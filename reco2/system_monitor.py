"""System / process / algorithm monitor for RECO3.

Collects OS-level metrics and manages external algorithm processes.
All control actions are restricted to an explicit allowlist.
"""

import logging
import os
import platform
import signal
import subprocess
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("reco3.system")

# ── Try psutil, fallback to /proc ───────────────────────────────
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False
    log.info("psutil not installed – using /proc fallback (limited metrics)")


# ══════════════════════════════════════════════════════════════════
#  Metrics Collection
# ══════════════════════════════════════════════════════════════════

def get_system_metrics() -> Dict[str, Any]:
    """Return CPU / memory / disk / network snapshot."""
    if _HAS_PSUTIL:
        return _metrics_psutil()
    return _metrics_proc()


def _metrics_psutil() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_count": psutil.cpu_count(),
        "mem_total_mb": round(vm.total / 1048576),
        "mem_used_mb": round(vm.used / 1048576),
        "mem_percent": vm.percent,
        "disk_total_gb": round(du.total / 1073741824, 1),
        "disk_used_gb": round(du.used / 1073741824, 1),
        "disk_percent": du.percent,
        "net_sent_mb": round(net.bytes_sent / 1048576, 1),
        "net_recv_mb": round(net.bytes_recv / 1048576, 1),
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "load_15m": round(load[2], 2),
        "platform": platform.system(),
        "python": platform.python_version(),
        "ts": time.time(),
    }


def _metrics_proc() -> Dict[str, Any]:
    """Minimal fallback using /proc (Linux only)."""
    cpu_pct = 0.0
    mem_pct = 0.0
    mem_total = 0
    mem_used = 0
    try:
        with open("/proc/stat") as f:
            line = f.readline()
            parts = line.split()
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            cpu_pct = round((1 - idle / max(total, 1)) * 100, 1)
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            lines = {l.split(":")[0]: int(l.split()[1]) for l in f if ":" in l}
            mem_total = lines.get("MemTotal", 0)
            mem_free = lines.get("MemAvailable", lines.get("MemFree", 0))
            mem_used = mem_total - mem_free
            mem_pct = round(mem_used / max(mem_total, 1) * 100, 1)
    except Exception:
        pass
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
    return {
        "cpu_percent": cpu_pct,
        "cpu_count": os.cpu_count() or 1,
        "mem_total_mb": round(mem_total / 1024),
        "mem_used_mb": round(mem_used / 1024),
        "mem_percent": mem_pct,
        "disk_total_gb": 0,
        "disk_used_gb": 0,
        "disk_percent": 0,
        "net_sent_mb": 0,
        "net_recv_mb": 0,
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "load_15m": round(load[2], 2),
        "platform": platform.system(),
        "python": platform.python_version(),
        "ts": time.time(),
    }


# ══════════════════════════════════════════════════════════════════
#  Process List
# ══════════════════════════════════════════════════════════════════

def get_top_processes(top_n: int = 10) -> List[Dict[str, Any]]:
    """Return top-N processes by CPU usage."""
    if not _HAS_PSUTIL:
        return []
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": round(info.get("cpu_percent", 0) or 0, 1),
                "mem": round(info.get("memory_percent", 0) or 0, 1),
                "status": info.get("status", "unknown"),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return procs[:top_n]


# ══════════════════════════════════════════════════════════════════
#  Algorithm Registry (external process management)
# ══════════════════════════════════════════════════════════════════

# Registered algorithms: name -> config
_registry: Dict[str, Dict[str, Any]] = {}
# Running processes: name -> Popen
_running: Dict[str, subprocess.Popen] = {}


def register_algorithm(name: str, command: List[str], cwd: Optional[str] = None,
                       env: Optional[Dict] = None) -> Dict[str, str]:
    """Register an external algorithm/process for monitoring and control."""
    _registry[name] = {
        "command": command,
        "cwd": cwd,
        "env": env,
        "registered_at": time.time(),
    }
    log.info(f"Algorithm registered: {name} -> {command}")
    return {"status": "registered", "name": name}


def get_algorithm_status() -> List[Dict[str, Any]]:
    """Return status of all registered algorithms."""
    result = []
    for name, cfg in _registry.items():
        proc = _running.get(name)
        running = False
        pid = None
        returncode = None
        if proc is not None:
            poll = proc.poll()
            if poll is None:
                running = True
                pid = proc.pid
            else:
                returncode = poll
        result.append({
            "name": name,
            "command": cfg["command"],
            "running": running,
            "pid": pid,
            "returncode": returncode,
        })
    return result


def control_algorithm(name: str, action: str) -> Dict[str, Any]:
    """Start / stop / restart a registered algorithm.

    Actions: "start", "stop", "restart", "status"
    """
    if name not in _registry:
        return {"error": "not_registered", "name": name}

    cfg = _registry[name]

    if action == "status":
        proc = _running.get(name)
        running = proc is not None and proc.poll() is None
        return {"name": name, "running": running, "pid": proc.pid if running else None}

    if action == "stop":
        proc = _running.get(name)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.info(f"Algorithm stopped: {name} (pid={proc.pid})")
            return {"name": name, "action": "stopped", "pid": proc.pid}
        return {"name": name, "action": "not_running"}

    if action == "start":
        proc = _running.get(name)
        if proc and proc.poll() is None:
            return {"name": name, "action": "already_running", "pid": proc.pid}
        env_merged = dict(os.environ)
        if cfg.get("env"):
            env_merged.update(cfg["env"])
        p = subprocess.Popen(
            cfg["command"],
            cwd=cfg.get("cwd"),
            env=env_merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _running[name] = p
        log.info(f"Algorithm started: {name} (pid={p.pid})")
        return {"name": name, "action": "started", "pid": p.pid}

    if action == "restart":
        control_algorithm(name, "stop")
        return control_algorithm(name, "start")

    return {"error": "unknown_action", "action": action}


# ══════════════════════════════════════════════════════════════════
#  Health Rules (for auto-monitor integration)
# ══════════════════════════════════════════════════════════════════

def evaluate_system_health(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate system metrics and return health status + alerts."""
    alerts = []
    status = "ok"

    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("mem_percent", 0)
    disk = metrics.get("disk_percent", 0)
    load_1m = metrics.get("load_1m", 0)
    cpu_count = metrics.get("cpu_count", 1)

    if cpu >= 95:
        alerts.append({"level": "critical", "msg": f"CPU {cpu}%"})
        status = "critical"
    elif cpu >= 80:
        alerts.append({"level": "warning", "msg": f"CPU {cpu}%"})
        if status != "critical":
            status = "warning"

    if mem >= 95:
        alerts.append({"level": "critical", "msg": f"Memory {mem}%"})
        status = "critical"
    elif mem >= 85:
        alerts.append({"level": "warning", "msg": f"Memory {mem}%"})
        if status != "critical":
            status = "warning"

    if disk >= 95:
        alerts.append({"level": "critical", "msg": f"Disk {disk}%"})
        status = "critical"
    elif disk >= 85:
        alerts.append({"level": "warning", "msg": f"Disk {disk}%"})
        if status != "critical":
            status = "warning"

    if load_1m > cpu_count * 2:
        alerts.append({"level": "warning", "msg": f"Load {load_1m} (cores={cpu_count})"})
        if status != "critical":
            status = "warning"

    return {"status": status, "alerts": alerts}
