import json, os, secrets, logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))

def _instance_dir() -> str:
    return os.environ.get("RECO3_INSTANCE_DIR") or os.path.join(_project_root(), "instance")

def config_path() -> str:
    return os.path.join(_instance_dir(), "config.json")

_DEFAULTS: Dict[str, Any] = {
    "host": "0.0.0.0", "port": 5001, "debug": False,
    "api_key_enabled": False, "api_keys": [],
    "llm_adapter": "auto", "llm_model": "",
    "psi_regen_threshold": 0.50, "psi_annot_threshold": 0.80,
    "max_regen_attempts": 2, "base_temperature": 0.7,
    "input_w_ambiguity": 0.20, "input_w_assertion": 0.25,
    "input_w_emotion": 0.30, "input_w_unrealistic": 0.25,
    "output_w_assertion": 0.30, "output_w_evidence": 0.30,
    "output_w_contradiction": 0.25, "output_w_provocative": 0.15,
    "agent_proxy_port": 8100, "agent_proxy_bind": "127.0.0.1",
}

def _secure_file(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError as e:
        logger.warning(f"Failed to secure file permissions for {path}: {e}")

def ensure_config() -> None:
    d = _instance_dir()
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError as e:
        logger.warning(f"Failed to secure directory permissions for {d}: {e}")
    p = config_path()
    if not os.path.exists(p):
        cfg = dict(_DEFAULTS)
        # Generate an API key but keep disabled by default.
        cfg["api_keys"] = [f"reco3_{secrets.token_hex(24)}"]
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except (IOError, json.JSONEncodeError) as e:
                os.close(fd)
                logger.error(f"Failed to write config file {p}: {e}")
                raise
            _secure_file(p)
        except (OSError, IOError, json.JSONEncodeError) as e:
            logger.error(f"Failed to create config file {p}: {e}")
            raise

def load_config() -> Dict[str, Any]:
    ensure_config()
    with open(config_path(), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # fill missing keys with defaults (forward compatible)
    for k, v in _DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg

def public_config(cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = dict(cfg or load_config())
    if "api_keys" in cfg:
        cfg["api_keys"] = ["***" for _ in (cfg.get("api_keys") or [])]
    return cfg
