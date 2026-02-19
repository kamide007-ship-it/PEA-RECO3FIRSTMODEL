import json, os, time, logging
from typing import Any, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)

HOME_DIR = Path.home()
STATE_DIR = HOME_DIR / ".reco3"
STATE_PATH = STATE_DIR / "agent_state.json"
LOG_PATH = STATE_DIR / "agent_logs.jsonl"

default_state: Dict[str, Any] = {
    "user_id": "default",
    "psi": 1.0, "T": 0.7, "T_base": 0.7,
    "k": 1.5, "eta": 0.01,
    "domains": {},
    "total_sessions": 0,
    "session_history": [],
    "daily_counts": {},
    "last_active": None,
}

def _now_ts() -> float:
    return time.time()

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

def _secure_dir(path: Path) -> None:
    try:
        os.chmod(str(path), 0o700)
    except OSError as e:
        logger.warning(f"Failed to secure directory permissions for {path}: {e}")

def ensure_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _secure_dir(STATE_DIR)

def load_state() -> Dict[str, Any]:
    ensure_dir()
    if not STATE_PATH.exists():
        save_state(dict(default_state))
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            j = json.load(f)
        out = dict(default_state)
        if isinstance(j, dict):
            out.update(j)
        return out
    except json.JSONDecodeError as e:
        logger.error(f"Agent state file corrupted at {STATE_PATH}, using defaults: {e}")
        return dict(default_state)
    except (OSError, IOError) as e:
        logger.error(f"Failed to read agent state file {STATE_PATH}: {e}")
        return dict(default_state)

def save_state(state: Dict[str, Any]) -> None:
    ensure_dir()
    tmp = str(STATE_PATH) + ".tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(STATE_PATH))
    except (OSError, IOError, json.JSONEncodeError) as e:
        logger.error(f"Failed to save state to {STATE_PATH}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError as cleanup_err:
            logger.warning(f"Failed to cleanup temp file {tmp}: {cleanup_err}")
        raise

def record_session(state: Dict[str, Any]) -> Dict[str, Any]:
    ts = _now_ts()
    iso = _now_iso()
    hist = state.get("session_history") or []
    if not isinstance(hist, list):
        hist = []
    hist.append(ts)
    if len(hist) > 200:
        hist = hist[-200:]
    state["session_history"] = hist
    day = iso.split("T", 1)[0]
    dc = state.get("daily_counts") or {}
    if not isinstance(dc, dict):
        dc = {}
    dc[day] = int(dc.get(day, 0) or 0) + 1
    state["daily_counts"] = dc
    state["total_sessions"] = int(state.get("total_sessions", 0) or 0) + 1
    state["last_active"] = iso
    return state

def get_domain_weight(state: Dict[str, Any], domain: str) -> float:
    dom = state.get("domains") or {}
    if not isinstance(dom, dict):
        return 1.0
    try:
        return float(dom.get(domain, 1.0))
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert domain weight to float for domain {domain}: {e}")
        return 1.0

def update_domain_weight(state: Dict[str, Any], domain: str, w: float) -> Dict[str, Any]:
    dom = state.get("domains") or {}
    if not isinstance(dom, dict):
        dom = {}
    dom[domain] = float(w)
    state["domains"] = dom
    return state

def append_log(entry: Dict[str, Any]) -> None:
    ensure_dir()
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, IOError, json.JSONEncodeError) as e:
        logger.error(f"Failed to append log entry to {LOG_PATH}: {e}")

def read_logs(limit: int = 20) -> List[Dict[str, Any]]:
    ensure_dir()
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, IOError) as e:
        logger.error(f"Failed to read log file {LOG_PATH}: {e}")
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse log line as JSON: {e}")
            continue
    return out

def reset_state() -> None:
    save_state(dict(default_state))
    try:
        if LOG_PATH.exists():
            LOG_PATH.unlink()
    except OSError as e:
        logger.warning(f"Failed to delete log file {LOG_PATH}: {e}")
