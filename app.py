import logging
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect

from reco2.engine import evaluate_payload, record_feedback, patrol, get_status, get_logs
from reco2.store import ensure_state_file
from reco2.orchestrator import get_orchestrator
from reco2.config import load_config, public_config
from reco2 import input_gate, output_gate

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("reco3")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_AS_ASCII"] = False
ensure_state_file()

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        cfg = load_config()
        if not cfg.get("api_key_enabled", False):
            return f(*args, **kwargs)
        key = (request.headers.get("X-API-Key")
               or request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
        valid_keys = cfg.get("api_keys", [])
        if not key or key not in valid_keys:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

# ── Pages ──────────────────────────────────────────────────────────

@app.get("/")
def page_index():
    return redirect("/r3", code=302)
@app.get("/r3")
def page_r3():
    return render_template("reco3.html")

@app.post("/api/evaluate")
@require_api_key
def api_evaluate():
    try:
        payload = request.get_json(force=True, silent=False)
        return jsonify(evaluate_payload(payload))
    except (OSError, IOError) as e:
        log.error(f"State file error in /api/evaluate: {e}")
        return jsonify({"error": "state_error", "detail": str(e)}), 500
    except (ValueError, TypeError) as e:
        log.error(f"Invalid payload in /api/evaluate: {e}")
        return jsonify({"error": "invalid_payload", "detail": str(e)}), 400
    except Exception as e:
        log.error(f"Unexpected error in /api/evaluate: {e}")
        return jsonify({"error": "internal_error"}), 500

@app.post("/api/feedback")
@require_api_key
def api_feedback():
    payload = request.get_json(force=True, silent=True) or {}
    res = record_feedback(payload)
    if isinstance(res, tuple):
        return jsonify(res[0]), res[1]
    return jsonify(res)

@app.post("/api/patrol")
@require_api_key
def api_patrol():
    return jsonify(patrol(manual=True))

@app.get("/api/status")
@require_api_key
def api_status():
    return jsonify(get_status())

@app.get("/api/logs")
@require_api_key
def api_logs():
    try:
        limit = int(request.args.get("limit", "50"))
    except (ValueError, TypeError) as e:
        log.warning(f"Failed to parse limit parameter: {e}")
        limit = 50
    return jsonify(get_logs(limit=limit))

@app.post("/api/r3/chat")
@require_api_key
def api_r3_chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = str(data.get("prompt", ""))
        domain = str(data.get("domain", "general"))
        max_tokens = int(data.get("max_tokens", 1024) or 1024)
        orch = get_orchestrator()
        res = orch.process(prompt, domain=domain, context=data.get("context") or {}, max_tokens=max_tokens)
        return jsonify(res)
    except RuntimeError as e:
        if "API" in str(e) or "api" in str(e).lower():
            log.error(f"LLM API error in /api/r3/chat: {e}")
            return jsonify({"error": "llm_api_error", "detail": str(e)}), 503
        log.error(f"Runtime error in /api/r3/chat: {e}")
        return jsonify({"error": "runtime_error", "detail": str(e)}), 500
    except (OSError, IOError) as e:
        log.error(f"State file error in /api/r3/chat: {e}")
        return jsonify({"error": "state_error", "detail": str(e)}), 500
    except Exception as e:
        log.error(f"Unexpected error in /api/r3/chat: {e}")
        return jsonify({"error": "internal_error"}), 500

@app.post("/api/r3/analyze_input")
@require_api_key
def api_r3_analyze_input():
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text", ""))
    cfg = load_config()
    res = input_gate.analyze(
        text,
        w_ambiguity=float(cfg.get("input_w_ambiguity", 0.20)),
        w_assertion=float(cfg.get("input_w_assertion", 0.25)),
        w_emotion=float(cfg.get("input_w_emotion", 0.30)),
        w_unrealistic=float(cfg.get("input_w_unrealistic", 0.25)),
    )
    return jsonify(res)

@app.post("/api/r3/analyze_output")
@require_api_key
def api_r3_analyze_output():
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text", ""))
    cfg = load_config()
    res = output_gate.analyze(
        text,
        w_assertion=float(cfg.get("output_w_assertion", 0.30)),
        w_evidence=float(cfg.get("output_w_evidence", 0.30)),
        w_contradiction=float(cfg.get("output_w_contradiction", 0.25)),
        w_provocative=float(cfg.get("output_w_provocative", 0.15)),
    )
    return jsonify(res)

@app.get("/api/r3/config")
@require_api_key
def api_r3_config():
    return jsonify(public_config(load_config()))

def main():
    import os
    cfg = load_config()

    # Initialize orchestrator and log LLM configuration
    orch = get_orchestrator()
    adapter = orch.get_active_adapter()
    model = orch.get_active_model()
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    log.info(f"LLM Configuration: adapter={adapter}, model={model}, has_openai_key={has_openai}, has_anthropic_key={has_anthropic}")

    app.run(host=cfg.get("host", "0.0.0.0"), port=int(cfg.get("port", 5001)), debug=bool(cfg.get("debug", False)))

if __name__ == "__main__":
    main()
