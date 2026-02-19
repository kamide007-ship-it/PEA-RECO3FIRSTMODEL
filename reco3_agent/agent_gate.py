import json, urllib.request, logging
from typing import Dict, Any, Optional
from reco3_agent import analyzer
from reco3_agent.state import append_log

logger = logging.getLogger(__name__)

def _post_json(url: str, payload: Dict[str, Any], timeout: int = 5) -> Optional[Dict[str, Any]]:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        j = json.loads(raw)
        return j if isinstance(j, dict) else None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response from {url}: {e}")
        return None
    except urllib.error.URLError as e:
        logger.warning(f"Failed to POST to {url}: {e}")
        return None
    except (IOError, TimeoutError) as e:
        logger.warning(f"Network error while POSTing to {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in _post_json for {url}: {e}")
        return None

def _rewrite_calm(text: str) -> str:
    t = (text or "").replace("!", "").replace("！", "")
    for bad in ["ふざけるな", "使えない", "いい加減にして", "急いで", "今すぐ", "早く"]:
        t = t.replace(bad, "")
    return "[冷静モードで再構成された入力]\n" + t.strip()

def evaluate_input(text: str, user_state: Dict[str, Any], reco3_url: str) -> Dict[str, Any]:
    local = analyzer.analyze_human(text, user_state)
    remote = _post_json(reco3_url.rstrip("/") + "/api/r3/analyze_input", {"text": text}) if reco3_url else None

    sev_map = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    local_sev = {"pass": 0, "warn": 1, "block": 2, "cool": 3}.get(local.get("action"), 0)
    remote_sev = sev_map.get((remote or {}).get("risk_level", "low"), 0) if remote else 0
    worst = "local" if local_sev >= remote_sev else "remote"

    action = local.get("action")
    tmod = float(local.get("temperature_modifier", 1.0))
    if remote and worst == "remote":
        action = {"low": "pass", "moderate": "warn", "high": "block", "critical": "cool"}.get(remote.get("risk_level"), "pass")
        tmod = float(remote.get("temperature_modifier", 1.0))

    rewritten = text
    rewritten_flag = False
    if action in ("warn", "block", "cool"):
        rewritten = _rewrite_calm(text)
        rewritten_flag = True

    result = {
        "local": local,
        "remote": remote,
        "worst": worst,
        "action": action,
        "temperature_modifier": tmod,
        "rewrite": rewritten_flag,
        "text": rewritten,
    }
    append_log({"type": "input_eval", "result": result})
    return result

def evaluate_output(text: str, reco3_url: str) -> Dict[str, Any]:
    remote = _post_json(reco3_url.rstrip("/") + "/api/r3/analyze_output", {"text": text}) if reco3_url else None
    append_log({"type": "output_eval", "remote": remote, "text_len": len(text or "")})
    return {"remote": remote}
