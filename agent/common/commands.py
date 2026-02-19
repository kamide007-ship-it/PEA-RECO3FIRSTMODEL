"""Command execution for RECO3 PC Agent.
Dispatches validated commands to OS-level operations.
"""

import logging
import subprocess
import platform

logger = logging.getLogger(__name__)


def execute_command(cmd_type: str, payload: dict, config: dict) -> dict:
    """Execute a validated command. Returns result dict."""
    handler = _HANDLERS.get(cmd_type)
    if not handler:
        return {"success": False, "error": f"No handler for {cmd_type}"}

    try:
        return handler(payload, config)
    except Exception as e:
        logger.error(f"Command execution error [{cmd_type}]: {e}")
        return {"success": False, "error": str(e)}


def _set_mode(payload: dict, config: dict) -> dict:
    """Switch agent operational mode."""
    mode = payload.get("mode", "NORMAL")
    logger.info(f"SET_MODE: {mode}")
    # In v1, mode is stored locally and affects agent behavior
    return {"success": True, "output": f"Mode set to {mode}", "mode": mode}


def _set_rate_limit(payload: dict, config: dict) -> dict:
    """Set rate limiting (placeholder for v1)."""
    endpoint = payload.get("endpoint", "")
    limit_rps = payload.get("limit_rps", 100)
    logger.info(f"SET_RATE_LIMIT: {endpoint} -> {limit_rps} rps")
    return {"success": True, "output": f"Rate limit set: {endpoint}={limit_rps}rps"}


def _notify_ops(payload: dict, config: dict) -> dict:
    """Send notification (local log in v1)."""
    severity = payload.get("severity", "info")
    message = payload.get("message", "")
    logger.info(f"NOTIFY_OPS [{severity}]: {message}")
    return {"success": True, "output": f"Notification sent: [{severity}] {message}"}


def _restart_process(payload: dict, config: dict) -> dict:
    """Restart a monitored process. STRONG COMMAND - requires dual-lock."""
    process_name = payload.get("process", "")
    if not process_name:
        return {"success": False, "error": "Missing process name"}

    # Find restart_cmd from config
    watch_procs = config.get("watch", {}).get("processes", [])
    proc_cfg = None
    for p in watch_procs:
        if p.get("name") == process_name:
            proc_cfg = p
            break

    if not proc_cfg:
        return {"success": False, "error": f"Process '{process_name}' not in watch list"}

    if not proc_cfg.get("allow_restart", False):
        return {"success": False, "error": f"Restart not allowed for '{process_name}'"}

    restart_cmd = proc_cfg.get("restart_cmd", "")
    if not restart_cmd:
        return {"success": False, "error": f"No restart_cmd configured for '{process_name}'"}

    logger.warning(f"EXECUTING RESTART: {process_name} -> {restart_cmd}")

    try:
        is_windows = platform.system().lower() == "windows"
        result = subprocess.run(
            restart_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            # On Windows, use cmd.exe; on Unix, use sh
            executable=None if is_windows else "/bin/sh",
        )
        output = result.stdout + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output[:2000],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out (60s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _stop_process(payload: dict, config: dict) -> dict:
    """Stop a monitored process. STRONG COMMAND."""
    process_name = payload.get("process", "")
    if not process_name:
        return {"success": False, "error": "Missing process name"}

    watch_procs = config.get("watch", {}).get("processes", [])
    proc_cfg = None
    for p in watch_procs:
        if p.get("name") == process_name:
            proc_cfg = p
            break

    if not proc_cfg:
        return {"success": False, "error": f"Process '{process_name}' not in watch list"}

    stop_cmd = proc_cfg.get("stop_cmd", "")
    if not stop_cmd:
        return {"success": False, "error": f"No stop_cmd configured for '{process_name}'"}

    logger.warning(f"EXECUTING STOP: {process_name} -> {stop_cmd}")

    try:
        is_windows = platform.system().lower() == "windows"
        result = subprocess.run(
            stop_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            executable=None if is_windows else "/bin/sh",
        )
        output = result.stdout + result.stderr
        return {
            "success": result.returncode == 0,
            "output": output[:2000],
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out (60s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _rollback(payload: dict, config: dict) -> dict:
    """Rollback operation. STRONG COMMAND. Placeholder for v1."""
    logger.warning("ROLLBACK requested - v1 placeholder")
    return {"success": True, "output": "Rollback acknowledged (v1 placeholder)"}


_HANDLERS = {
    "SET_MODE": _set_mode,
    "SET_RATE_LIMIT": _set_rate_limit,
    "NOTIFY_OPS": _notify_ops,
    "RESTART_PROCESS": _restart_process,
    "STOP_PROCESS": _stop_process,
    "ROLLBACK": _rollback,
}
