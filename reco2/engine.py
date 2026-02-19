import math, uuid, datetime, logging
from typing import Dict, Any, Tuple, List
from reco2.store import load_state, save_state

logger = logging.getLogger(__name__)

def _euclidean_distance(I: Dict[str, float], P: Dict[str, Dict[str, float]]) -> float:
    """推論(I)と証拠(P)のユークリッド距離"""
    keys = sorted(set(I.keys()) & set(P.keys()))
    if not keys:
        keys = sorted(set(I.keys()) | set(P.keys()))
    s = 0.0
    for k in keys:
        i = float(I.get(k, 0.0))
        e = P.get(k, {})
        m = float(e.get("median", 0.0)) if isinstance(e, dict) else 0.0
        d = i - m
        s += d * d
    return math.sqrt(s)

def _context_match_score(context: Dict[str, Any]) -> float:
    conf = float(context.get("confidence", 0.0))
    conf = max(0.0, min(1.0, conf))
    domain_known = bool(context.get("domain_known", False))
    missing = int(context.get("missing_fields", 0) or 0)
    warnings = int(context.get("warnings", 0) or 0)
    score = conf
    if domain_known:
        score = min(1.0, score + 0.10)
    score -= 0.03 * missing
    score -= 0.04 * warnings
    return max(0.0, min(1.0, score))

def _purity(context: Dict[str, Any]) -> float:
    s = _context_match_score(context)
    if not bool(context.get("domain_known", False)):
        s *= 0.90
    return max(0.0, min(1.0, s))

def _alpha(context_match_score: float) -> float:
    return 1.0 + (context_match_score * 0.2)

def _beta(purity: float) -> float:
    if purity > 0.8:
        return 1.0
    return max(0.5, purity)

def _temperature(T_base: float, k: float, D: float) -> float:
    """T = T_base * exp(-k * D)"""
    T = T_base * math.exp(-k * D)
    return max(0.1, T)

def _integrity(T_final: float, alpha: float, beta: float) -> float:
    """ψ = (1/T) * α * β"""
    return (1.0 / T_final) * alpha * beta

def _verdict_from_psi(psi: float) -> Tuple[str, str]:
    if psi >= 1.2:
        return "reliable", "信頼できる"
    if psi >= 0.8:
        return "moderate", "ふつう"
    return "suspect", "あやしい"

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

def _confidence_adjusted(base_conf: float, psi: float) -> float:
    base_conf = max(0.0, min(1.0, float(base_conf)))
    factor = max(0.6, min(1.25, psi / 1.2))
    return max(0.0, min(1.0, base_conf * factor))

def _get_domain_weight(state: Dict[str, Any], domain: str) -> float:
    dom = state.get("domains", {})
    w = dom.get(domain, 1.0) if isinstance(dom, dict) else 1.0
    try:
        return float(w)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert domain weight to float for domain {domain}: {e}")
        return 1.0

def _set_domain_weight(state: Dict[str, Any], domain: str, w: float) -> None:
    if "domains" not in state or not isinstance(state["domains"], dict):
        state["domains"] = {}
    state["domains"][domain] = float(w)

def _append_session_log(state: Dict[str, Any], entry: Dict[str, Any]) -> None:
    logs = state.get("session_logs", [])
    if not isinstance(logs, list):
        logs = []
    logs.append(entry)
    if len(logs) > 2000:
        logs = logs[-2000:]
    state["session_logs"] = logs

def evaluate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON")
    inference = payload.get("inference", {})
    evidence = payload.get("evidence", {})
    context = payload.get("context", {})
    if not isinstance(inference, dict) or not isinstance(evidence, dict) or not isinstance(context, dict):
        raise ValueError("Invalid payload types")
    domain = str(context.get("domain", "")).strip()
    if not domain:
        raise ValueError("context.domain is required")

    state = load_state()
    D = _euclidean_distance({k: float(v) for k, v in inference.items()}, evidence)
    k = float(state.get("k", 1.5))
    eta = float(state.get("eta", 0.01))
    T_base = float(state.get("T_base", 0.8))

    cms = _context_match_score(context)
    purity = _purity(context)
    alpha = _alpha(cms)
    beta = _beta(purity)
    T = _temperature(T_base, k, D)
    psi = _integrity(T, alpha, beta)

    base_conf = float(context.get("confidence", 0.0))
    conf_adj = _confidence_adjusted(base_conf, psi)
    verdict, verdict_ja = _verdict_from_psi(psi)

    session_id = str(uuid.uuid4())
    ts = _now_iso()
    state["total_sessions"] = int(state.get("total_sessions", 0) or 0) + 1
    total_sessions = state["total_sessions"]

    entry = {
        "session_id": session_id, "ts": ts, "domain": domain,
        "D": round(D, 6), "T": round(T, 6), "psi": round(psi, 6),
        "verdict": verdict, "reward": None, "feedback": None,
    }
    _append_session_log(state, entry)
    save_state(state)

    if total_sessions % 10 == 0:
        patrol(manual=False)

    st2 = load_state()
    return {
        "session_id": session_id,
        "deviation": round(D, 6),
        "temperature": round(T, 6),
        "integrity": round(psi, 6),
        "confidence_adjusted": round(conf_adj, 6),
        "verdict": verdict,
        "verdict_ja": verdict_ja,
        "meta": {
            "k": float(st2.get("k", k)),
            "eta": float(st2.get("eta", eta)),
            "total_sessions": total_sessions,
            "domain_weight": _get_domain_weight(st2, domain),
            "context_match_score": round(cms, 6),
            "purity": round(purity, 6),
            "alpha": round(alpha, 6),
            "beta": round(beta, 6),
        }
    }

def record_feedback(payload: Dict[str, Any]):
    if not isinstance(payload, dict):
        return {"error": "invalid_json"}, 400
    session_id = str(payload.get("session_id", "")).strip()
    domain = str(payload.get("domain", "")).strip()
    fb = str(payload.get("feedback", "")).strip()
    if not session_id:
        return {"error": "session_id_required"}, 400
    if not domain:
        return {"error": "domain_required"}, 400
    if fb not in ("good", "bad", "recalculate"):
        return {"error": "invalid_feedback"}, 400

    R = 1.0 if fb == "good" else (0.3 if fb == "recalculate" else -1.0)
    state = load_state()
    used = state.get("used_session_ids", {})
    if not isinstance(used, dict):
        used = {}
    if session_id in used:
        return {"status": "duplicate_ignored", "domain": domain}

    used[session_id] = _now_iso()
    state["used_session_ids"] = used
    eta = float(state.get("eta", 0.01))
    W_old = _get_domain_weight(state, domain)
    W_new = W_old + (eta * R)
    _set_domain_weight(state, domain, W_new)

    logs = state.get("session_logs", [])
    if isinstance(logs, list):
        for i in range(len(logs) - 1, -1, -1):
            if logs[i].get("session_id") == session_id:
                logs[i]["reward"] = R
                logs[i]["feedback"] = fb
                break
        state["session_logs"] = logs
    save_state(state)
    return {"status": "recorded", "reward": R, "new_weight": round(W_new, 6), "domain": domain}

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def patrol(manual: bool = True) -> Dict[str, Any]:
    state = load_state()
    logs = state.get("session_logs", [])
    if not isinstance(logs, list) or not logs:
        return {"adjusted": False, "reason": "no_logs", "new_k": state.get("k", 1.5), "new_eta": state.get("eta", 0.01)}

    window = logs[-10:] if len(logs) >= 10 else logs[:]
    Ds = [float(x.get("D", 0.0)) for x in window]
    Rs = [x.get("reward", 0.0) for x in window if x.get("reward") is not None]
    psis = [float(x.get("psi", 0.0)) for x in window]
    avgD = sum(Ds) / max(1, len(Ds))
    sumR = sum(float(r) for r in Rs)
    avgPsi = sum(psis) / max(1, len(psis))

    k = float(state.get("k", 1.5))
    eta = float(state.get("eta", 0.01))
    adjusted = False
    reasons = []

    if avgD > 0.3 and sumR < 0:
        k += 0.1; eta *= 1.05; adjusted = True
        reasons.append("avgD>0.3 & sumR<0 -> strictify")
    if avgD < 0.1 and sumR > 0:
        k -= 0.05; adjusted = True
        reasons.append("avgD<0.1 & sumR>0 -> relax")
    if avgD > 0.3 and sumR > 0:
        eta *= 1.02; adjusted = True
        reasons.append("avgD>0.3 & sumR>0 -> learn faster")
    if avgPsi < 0.5:
        k += 0.05; adjusted = True
        reasons.append("avgPsi<0.5 -> tighten")

    k = _clamp(k, float(state.get("k_min", 0.5)), float(state.get("k_max", 5.0)))
    eta = _clamp(eta, float(state.get("eta_min", 0.001)), float(state.get("eta_max", 0.1)))
    state["k"] = k
    state["eta"] = eta
    save_state(state)

    return {
        "adjusted": adjusted,
        "reason": "; ".join(reasons) if reasons else "no_change",
        "new_k": round(k, 6), "new_eta": round(eta, 6),
        "window": {"avgD": round(avgD, 6), "sumR": round(sumR, 6), "avgPsi": round(avgPsi, 6), "window_size": len(window)},
        "manual": manual,
    }

def get_status() -> Dict[str, Any]:
    import os
    state = load_state()
    logs = state.get("session_logs", [])
    avgD = 0.0
    if isinstance(logs, list) and logs:
        slice_ = logs[-200:]
        avgD = sum(float(x.get("D", 0.0)) for x in slice_) / max(1, len(slice_))
    dist = {"reliable": 0, "moderate": 0, "suspect": 0}
    if isinstance(logs, list):
        for x in logs[-200:]:
            v = x.get("verdict")
            if v in dist:
                dist[v] += 1
    total = sum(dist.values()) or 1
    dist_pct = {k: round(v / total, 4) for k, v in dist.items()}
    total_sessions = int(state.get("total_sessions", 0) or 0)
    to_next = 10 - (total_sessions % 10) if (total_sessions % 10) != 0 else 10
    dom = state.get("domains", {})
    domains = []
    if isinstance(dom, dict):
        for d, w in dom.items():
            domains.append({"domain": d, "weight": float(w)})
    domains.sort(key=lambda x: (-x["weight"], x["domain"]))

    # Get active LLM adapter and model info
    from reco2.orchestrator import get_orchestrator
    try:
        orch = get_orchestrator()
        active_adapter = orch.get_active_adapter()
        active_model = orch.get_active_model()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to get orchestrator info: {e}")
        active_adapter = "unknown"
        active_model = "unknown"

    # Check API key availability (without exposing the keys)
    dual_keys = {
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }

    # API Key protection status (safe to expose - no secrets revealed)
    api_key_mode = os.environ.get("API_KEY_MODE", "enforce").strip().lower()
    api_key_header = os.environ.get("API_KEY_HEADER", "X-API-Key").strip()
    api_key_has_key = bool(os.environ.get("API_KEY", "").strip())

    api_key_protection = {
        "enabled": api_key_mode == "enforce" and api_key_has_key,
        "mode": api_key_mode,
        "header": api_key_header,
    }

    return {
        "k": float(state.get("k", 1.5)), "eta": float(state.get("eta", 0.01)),
        "total_sessions": total_sessions, "avg_deviation": round(avgD, 6),
        "to_next_patrol": to_next, "domains": domains,
        "verdict_distribution": dist, "verdict_distribution_pct": dist_pct,
        "ranges": {
            "k": [float(state.get("k_min", 0.5)), float(state.get("k_max", 5.0))],
            "eta": [float(state.get("eta_min", 0.001)), float(state.get("eta_max", 0.1))],
        },
        "active_llm_adapter": active_adapter,
        "active_llm_model": active_model,
        "dual_keys": dual_keys,
        "api_key_protection": api_key_protection,
    }

def get_logs(limit: int = 50) -> List[Dict[str, Any]]:
    state = load_state()
    logs = state.get("session_logs", [])
    if not isinstance(logs, list):
        return []
    return list(reversed(logs[-limit:]))
