"""System metrics collection using psutil."""

import logging
import platform

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


def collect_metrics(config: dict) -> dict:
    """Collect CPU, MEM, DISK, NET, and process metrics."""
    if psutil is None:
        logger.warning("psutil not installed, returning empty metrics")
        return {}

    metrics = {}

    # CPU
    try:
        metrics["cpu_percent"] = psutil.cpu_percent(interval=1)
        metrics["cpu_count"] = psutil.cpu_count()
    except Exception as e:
        logger.warning(f"CPU metric error: {e}")

    # Memory
    try:
        mem = psutil.virtual_memory()
        metrics["mem_percent"] = mem.percent
        metrics["mem_used_mb"] = round(mem.used / 1048576, 1)
        metrics["mem_total_mb"] = round(mem.total / 1048576, 1)
    except Exception as e:
        logger.warning(f"Memory metric error: {e}")

    # Disk
    try:
        disk = psutil.disk_usage("/")
        metrics["disk_percent"] = disk.percent
        metrics["disk_used_gb"] = round(disk.used / 1073741824, 1)
        metrics["disk_total_gb"] = round(disk.total / 1073741824, 1)
    except Exception as e:
        logger.warning(f"Disk metric error: {e}")

    # Network
    try:
        net = psutil.net_io_counters()
        metrics["net_bytes_sent"] = net.bytes_sent
        metrics["net_bytes_recv"] = net.bytes_recv
    except Exception as e:
        logger.warning(f"Network metric error: {e}")

    # Platform info
    metrics["platform"] = platform.system().lower()
    metrics["hostname"] = platform.node()

    # Monitored processes
    watch_procs = config.get("watch", {}).get("processes", [])
    if watch_procs:
        metrics["processes"] = _check_processes(watch_procs)

    return metrics


def _check_processes(watch_list: list) -> list:
    """Check status of monitored processes."""
    if psutil is None:
        return []

    results = []
    all_procs = {p.info["name"]: p.info for p in psutil.process_iter(["pid", "name", "status"])}

    for watch in watch_list:
        name = watch.get("name", "")
        proc_info = all_procs.get(name)
        results.append({
            "name": name,
            "running": proc_info is not None,
            "pid": proc_info["pid"] if proc_info else None,
            "status": proc_info["status"] if proc_info else "not_found",
        })

    return results
