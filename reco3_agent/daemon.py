import os, signal, subprocess, sys, time, logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

PID_PATH = Path.home() / ".reco3" / "reco3_agent.pid"

def _ensure_dir():
    d = PID_PATH.parent
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(d), 0o700)
    except OSError as e:
        logger.warning(f"Failed to secure directory permissions for {d}: {e}")

def start(port: int = 8100, bind: str = "127.0.0.1") -> Dict[str, Any]:
    _ensure_dir()
    if PID_PATH.exists():
        st = status()
        if st.get("running"):
            return {"status": "already_running", **st}
        try:
            PID_PATH.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete existing PID file {PID_PATH}: {e}")
    cmd = [sys.executable, "-c", f"from reco3_agent.proxy import run_proxy; run_proxy(port={int(port)}, bind='{bind}')"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        logger.error(f"Failed to start daemon process: {e}")
        return {"status": "failed", "error": str(e)}
    try:
        PID_PATH.write_text(str(p.pid), encoding="utf-8")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write PID file {PID_PATH}: {e}")
        return {"status": "failed", "error": str(e)}
    try:
        os.chmod(str(PID_PATH), 0o600)
    except OSError as e:
        logger.warning(f"Failed to secure PID file permissions for {PID_PATH}: {e}")
    time.sleep(0.05)
    return {"status": "started", "pid": p.pid, "port": int(port), "bind": bind}

def stop() -> Dict[str, Any]:
    _ensure_dir()
    if not PID_PATH.exists():
        return {"status": "not_running"}
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError, IOError) as e:
        logger.error(f"Failed to read PID from {PID_PATH}: {e}")
        return {"status": "failed", "error": str(e)}

    if pid <= 0:
        logger.warning(f"Invalid PID value {pid} in {PID_PATH}")
        try:
            PID_PATH.unlink()
        except OSError as e:
            logger.warning(f"Failed to delete PID file {PID_PATH}: {e}")
        return {"status": "invalid_pid", "pid": pid}

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        logger.warning(f"Failed to send SIGTERM to process {pid}: {e}")
    try:
        PID_PATH.unlink()
    except OSError as e:
        logger.warning(f"Failed to delete PID file {PID_PATH}: {e}")
    return {"status": "stopped", "pid": pid}

def status() -> Dict[str, Any]:
    _ensure_dir()
    if not PID_PATH.exists():
        return {"running": False}
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError, IOError) as e:
        logger.warning(f"Failed to read PID from {PID_PATH}: {e}")
        return {"running": False}

    if pid <= 0:
        logger.warning(f"Invalid PID value {pid} in {PID_PATH}")
        return {"running": False, "pid": pid}

    try:
        os.kill(pid, 0)
        return {"running": True, "pid": pid}
    except OSError as e:
        logger.debug(f"Process {pid} is not running: {e}")
        return {"running": False, "pid": pid}
