import logging
import os
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, session

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
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
ensure_state_file()

# ── API Key Configuration ──────────────────────────────────────

def _get_api_key_config():
    """Get API key configuration from environment variables

    Environment variables:
    - API_KEY: The actual API key (required for enforce mode)
    - API_KEY_MODE: "enforce" (default) or "off" (disable auth)
    - API_KEY_HEADER: Header name to check (default "X-API-Key")
    - API_KEY_BYPASS_PATHS: Comma-separated paths that don't need auth (overrides defaults)
    """
    api_key = os.getenv("API_KEY", "").strip()
    api_key_mode = os.getenv("API_KEY_MODE", "enforce").strip().lower()
    api_key_header = os.getenv("API_KEY_HEADER", "X-API-Key").strip()

    # Default bypass paths (PWA static files + pages)
    default_bypass = [
        "/",
        "/r3",
        "/health",
        "/favicon.ico",
        "/manifest.webmanifest",
        "/static/manifest.webmanifest",
        "/service-worker.js",
        "/static/service-worker.js",
    ]

    # Allow override via environment variable
    bypass_paths_str = os.getenv("API_KEY_BYPASS_PATHS", "").strip()
    if bypass_paths_str:
        bypass_paths = [p.strip() for p in bypass_paths_str.split(",") if p.strip()]
    else:
        bypass_paths = default_bypass

    return {
        "enabled": api_key_mode == "enforce" and bool(api_key),
        "api_key": api_key,
        "mode": api_key_mode,
        "header": api_key_header,
        "bypass_paths": bypass_paths,
        "has_key": bool(api_key),
    }

def _should_bypass_auth(path):
    """Check if request path should bypass API key authentication"""
    cfg = _get_api_key_config()

    # Exact match
    if path in cfg["bypass_paths"]:
        return True

    # Wildcard match for /static/*
    if path.startswith("/static/"):
        for bp in cfg["bypass_paths"]:
            if bp == "/static/*":
                return True

    return False

@app.before_request
def check_api_key():
    """Global API key validation middleware for /api/* endpoints"""
    cfg = _get_api_key_config()

    # Skip if mode is "off"
    if cfg["mode"] != "enforce":
        return

    # Skip if path bypasses auth
    if _should_bypass_auth(request.path):
        return

    # Only enforce for /api/* paths
    if not request.path.startswith("/api/"):
        return

    # PWA session auth: if user visited /r3 and has valid session, allow
    # /api/r3/*, /api/status, /api/logs, /api/feedback (needed by auto-monitor and PWA)
    _pwa_paths = ("/api/r3/", "/api/status", "/api/logs", "/api/feedback")
    if session.get("r3") and request.path.startswith(_pwa_paths):
        return

    # Validate API key
    key = request.headers.get(cfg["header"], "").strip()
    if not key or key != cfg["api_key"]:
        log.warning(f"API request rejected (invalid/missing key): {request.path}")
        return jsonify({"error": "unauthorized"}), 401

def require_api_key(f):
    """Decorator for backwards compatibility (now uses global middleware)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Global before_request already handles validation for /api/* paths
        # This decorator is kept for compatibility but is now largely redundant
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
    session["r3"] = True
    return render_template("reco3.html")

# ── PWA Assets (Root-level for Service Worker scope) ────────────────

@app.get("/manifest.webmanifest")
def pwa_manifest():
    """Serve manifest from root for PWA installation"""
    return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

@app.get("/service-worker.js")
def pwa_service_worker():
    """Serve Service Worker from root to control entire app scope"""
    return send_from_directory(app.static_folder, "service-worker.js", mimetype="application/javascript")

@app.get("/favicon.ico")
def pwa_favicon():
    """Serve favicon from root"""
    return send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon")

# ── API Routes ──────────────────────────────────────────────────────
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
def api_r3_chat():
    # セッション認証を優先（PWA用）。セッションが有効なら API_KEY チェックをスキップ
    if not session.get("r3"):
        # セッション無効な場合、API_KEY による認証を試みる（外部API呼び出し用）
        if os.getenv("API_KEY_MODE", "enforce").strip().lower() == "enforce":
            expected_key = os.getenv("API_KEY", "").strip()
            if not expected_key:
                log.warning(f"API request rejected (no session, API_KEY not configured): {request.path}")
                return jsonify({"error": "unauthorized"}), 401
            api_key_header = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
            api_key = request.headers.get(api_key_header, "").strip()
            if not api_key or api_key != expected_key:
                log.warning(f"API request rejected (no session, invalid API key): {request.path}")
                return jsonify({"error": "unauthorized"}), 401
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
    cfg = load_config()

    # Check SECRET_KEY configuration
    secret_key_env = os.getenv("SECRET_KEY")
    if not secret_key_env or secret_key_env == "dev-key-change-in-production":
        log.warning(f"⚠️  SECRET_KEY not set or using default dev key - session authentication will NOT work in production!")

    # Log LLM configuration
    orch = get_orchestrator()
    adapter = orch.get_active_adapter()
    model = orch.get_active_model()
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    log.info(f"LLM Configuration: adapter={adapter}, model={model}, has_openai_key={has_openai}, has_anthropic_key={has_anthropic}")

    # Log API key configuration
    api_cfg = _get_api_key_config()
    is_prod = os.getenv("FLASK_ENV", "development").lower() == "production"
    if api_cfg["mode"] == "enforce":
        if api_cfg["has_key"]:
            log.info(f"API Key Protection: ENABLED (mode=enforce, header={api_cfg['header']})")
        else:
            msg = "API Key Protection: DISABLED - API_KEY not set"
            if is_prod:
                log.warning(f"⚠️  {msg} (running in production!)")
            else:
                log.info(msg)
    else:
        log.info(f"API Key Protection: DISABLED (mode=off)")

    app.run(host=cfg.get("host", "0.0.0.0"), port=int(cfg.get("port", 5001)), debug=bool(cfg.get("debug", False)))

if __name__ == "__main__":
    main()
