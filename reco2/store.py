import json, os, logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))

def _instance_dir() -> str:
    # Test-friendly override
    return os.environ.get("RECO3_INSTANCE_DIR") or os.path.join(_project_root(), "instance")

def state_path() -> str:
    return os.path.join(_instance_dir(), "resonance_state.json")

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

def default_state() -> Dict[str, Any]:
    return {
        "k": 1.5,
        "eta": 0.01,
        "T_base": 0.8,
        "k_min": 0.5,
        "k_max": 5.0,
        "eta_min": 0.001,
        "eta_max": 0.1,
        "total_sessions": 0,
        "domains": {},
        "used_session_ids": {},
        "session_logs": [],
        "last_patrol_at_sessions": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

def _secure_dir(path: str) -> None:
    """ディレクトリを owner-only にする (macOS/Linux)"""
    try:
        os.chmod(path, 0o700)
    except OSError as e:
        logger.warning(f"Failed to secure directory permissions for {path}: {e}")

def ensure_state_file() -> None:
    d = _instance_dir()
    os.makedirs(d, exist_ok=True)
    _secure_dir(d)
    sp = state_path()
    if not os.path.exists(sp):
        save_state(default_state())

def load_state() -> Dict[str, Any]:
    ensure_state_file()
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"State file corrupted at {state_path()}, using defaults: {e}")
        return default_state()
    except (OSError, IOError) as e:
        logger.error(f"Failed to read state file {state_path()}: {e}")
        return default_state()

def save_state(state: Dict[str, Any]) -> None:
    state["updated_at"] = _now_iso()
    sp = state_path()
    tmp = sp + ".tmp"
    try:
        # owner-only file
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, sp)
    except (OSError, IOError, json.JSONEncodeError) as e:
        logger.error(f"Failed to save state to {sp}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as cleanup_err:
            logger.warning(f"Failed to cleanup temp file {tmp}: {cleanup_err}")
        raise
