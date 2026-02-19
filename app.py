import json
import logging
import os
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect, send_from_directory, session

from reco2.engine import evaluate_payload, record_feedback, patrol, get_status, get_logs
from reco2.store import ensure_state_file
from reco2.orchestrator import get_orchestrator
from reco2.config import load_config, public_config
from reco2 import input_gate, output_gate
from reco2.system_monitor import get_system_metrics, get_top_processes, evaluate_system_health, get_algorithm_status, control_algorithm, register_algorithm
from reco2.db import (init_db, WebTargets, Observations, Incidents, Suggestions,
                       Feedback, AuditLog, AgentStatus, AgentLogs, AgentCommands, Approvals)
from reco2.web_monitor_scheduler import start_monitoring, stop_monitoring
from reco2.suggestion_engine import generate_suggestions_for_incident
from reco2.learning_engine import run_learning_job

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("reco3")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_AS_ASCII"] = False
app.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
ensure_state_file()
init_db()  # Initialize SQLite database on startup
start_monitoring()  # Start web monitoring scheduler

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

    # Only enforce for /api/* paths; /agent/* uses its own auth
    if not request.path.startswith("/api/"):
        return

    # PWA session auth: if user visited /r3 and has valid session, allow
    # /api/r3/*, /api/status, /api/logs, /api/feedback (needed by auto-monitor and PWA)
    _pwa_paths = ("/api/r3/", "/api/status", "/api/logs", "/api/feedback", "/api/system",
                  "/api/agents", "/api/agent-commands", "/api/config/test-mode")
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

@app.get("/b2b")
def page_b2b():
    return render_template("b2b.html")

@app.get("/spec")
def page_spec():
    return render_template("spec.html")

@app.get("/tech")
def page_tech():
    return render_template("tech.html")

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

# ── System Monitor Routes ─────────────────────────────────────────

@app.get("/api/system")
@require_api_key
def api_system():
    metrics = get_system_metrics()
    health = evaluate_system_health(metrics)
    return jsonify({"metrics": metrics, "health": health})

@app.get("/api/system/processes")
@require_api_key
def api_system_processes():
    top_n = int(request.args.get("top", "10"))
    return jsonify(get_top_processes(top_n=top_n))

@app.get("/api/system/algorithms")
@require_api_key
def api_system_algorithms():
    return jsonify(get_algorithm_status())

@app.post("/api/system/algorithms/<name>")
@require_api_key
def api_system_algorithm_control(name):
    data = request.get_json(force=True, silent=True) or {}
    action = str(data.get("action", "status"))
    return jsonify(control_algorithm(name, action))

# ── Web Monitoring Routes ──────────────────────────────────────────

@app.post("/api/web-targets")
@require_api_key
def api_create_web_target():
    """Create web monitoring target."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        org_id = data.get("org_id", "default")

        target_id = WebTargets.create(
            name=data.get("name", "Unnamed"),
            url=data.get("url", ""),
            method=data.get("method", "GET"),
            interval_sec=int(data.get("interval_sec", 300)),
            expected_status=int(data.get("expected_status", 200)),
            expected_latency_ms=int(data.get("expected_latency_ms", 1000)),
            tags=data.get("tags", []),
            org_id=org_id,
        )

        AuditLog.log(
            actor="system:api",
            event_type="create_web_target",
            ref_id=target_id,
            payload={"url": data.get("url"), "name": data.get("name")},
            org_id=org_id,
        )

        return jsonify({"id": target_id, "status": "created"})
    except Exception as e:
        log.error(f"Error creating web target: {e}")
        return jsonify({"error": str(e)}), 400

@app.get("/api/web-targets")
@require_api_key
def api_list_web_targets():
    """List web monitoring targets."""
    try:
        org_id = request.args.get("org_id", "default")
        targets = WebTargets.list_enabled(org_id=org_id)
        return jsonify({"targets": targets, "count": len(targets)})
    except Exception as e:
        log.error(f"Error listing web targets: {e}")
        return jsonify({"error": str(e)}), 500

@app.get("/api/web-targets/<target_id>")
@require_api_key
def api_get_web_target(target_id):
    """Get web target details."""
    try:
        target = WebTargets.get_by_id(target_id)
        if not target:
            return jsonify({"error": "not_found"}), 404

        # Get recent observations for this target
        org_id = target.get("org_id", "default")
        recent_obs = Observations.list_recent(
            source_type="web",
            limit=20,
            org_id=org_id,
        )
        target_obs = [o for o in recent_obs if o.get("source_id") == target_id]

        return jsonify({"target": target, "recent_observations": target_obs})
    except Exception as e:
        log.error(f"Error getting web target: {e}")
        return jsonify({"error": str(e)}), 500

@app.delete("/api/web-targets/<target_id>")
@require_api_key
def api_delete_web_target(target_id):
    """Delete web monitoring target."""
    try:
        target = WebTargets.get_by_id(target_id)
        if not target:
            return jsonify({"error": "not_found"}), 404

        WebTargets.delete(target_id)

        AuditLog.log(
            actor="system:api",
            event_type="delete_web_target",
            ref_id=target_id,
            payload={"url": target.get("url")},
            org_id=target.get("org_id", "default"),
        )

        return jsonify({"status": "deleted"})
    except Exception as e:
        log.error(f"Error deleting web target: {e}")
        return jsonify({"error": str(e)}), 400

@app.get("/api/incidents")
@require_api_key
def api_list_incidents():
    """List incidents by status."""
    try:
        status = request.args.get("status", "open")
        org_id = request.args.get("org_id", "default")
        limit = int(request.args.get("limit", 50))

        incidents = Incidents.list_by_status(status, org_id=org_id, limit=limit)
        return jsonify({"incidents": incidents, "count": len(incidents)})
    except Exception as e:
        log.error(f"Error listing incidents: {e}")
        return jsonify({"error": str(e)}), 500

@app.get("/api/incidents/<incident_id>")
@require_api_key
def api_get_incident(incident_id):
    """Get incident details with suggestions."""
    try:
        incident = Incidents.get_by_id(incident_id)
        if not incident:
            return jsonify({"error": "not_found"}), 404

        org_id = incident.get("org_id", "default")
        suggestions = Suggestions.list_by_incident(incident_id, org_id=org_id)

        return jsonify({"incident": incident, "suggestions": suggestions})
    except Exception as e:
        log.error(f"Error getting incident: {e}")
        return jsonify({"error": str(e)}), 500

@app.post("/api/incidents/<incident_id>/suggestions")
@require_api_key
def api_generate_suggestions(incident_id):
    """Generate suggestions for incident (rule-based and AI)."""
    try:
        incident = Incidents.get_by_id(incident_id)
        if not incident:
            return jsonify({"error": "not_found"}), 404

        org_id = incident.get("org_id", "default")
        include_ai = request.args.get("ai", "true").lower() == "true"

        count = generate_suggestions_for_incident(
            incident,
            org_id=org_id,
            include_ai=include_ai,
        )

        AuditLog.log(
            actor="system:api",
            event_type="generate_suggestions",
            ref_id=incident_id,
            payload={"count": count, "include_ai": include_ai},
            org_id=org_id,
        )

        return jsonify({"status": "generated", "count": count})
    except Exception as e:
        log.error(f"Error generating suggestions: {e}")
        return jsonify({"error": str(e)}), 500

@app.get("/api/suggestions/<suggestion_id>")
@require_api_key
def api_get_suggestion(suggestion_id):
    """Get suggestion details with feedback."""
    try:
        suggestion = Suggestions.get_by_id(suggestion_id)
        if not suggestion:
            return jsonify({"error": "not_found"}), 404

        feedback_list = Feedback.list_by_suggestion(suggestion_id)

        # Calculate feedback statistics
        good_count = sum(1 for f in feedback_list if f.get("vote") == "good")
        bad_count = sum(1 for f in feedback_list if f.get("vote") == "bad")
        total_feedback = len(feedback_list)
        good_ratio = good_count / total_feedback if total_feedback > 0 else 0.0

        return jsonify({
            "suggestion": suggestion,
            "feedback": feedback_list,
            "feedback_stats": {
                "total": total_feedback,
                "good": good_count,
                "bad": bad_count,
                "good_ratio": good_ratio,
            }
        })
    except Exception as e:
        log.error(f"Error getting suggestion: {e}")
        return jsonify({"error": str(e)}), 500

@app.post("/api/feedback")
@require_api_key
def api_submit_feedback():
    """Submit Good/Bad feedback on suggestion."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        suggestion_id = data.get("suggestion_id")
        vote = data.get("vote", "").lower()
        comment = data.get("comment", "")
        user_id = data.get("user_id", None)

        if not suggestion_id or vote not in ("good", "bad"):
            return jsonify({"error": "invalid_parameters"}), 400

        suggestion = Suggestions.get_by_id(suggestion_id)
        if not suggestion:
            return jsonify({"error": "suggestion_not_found"}), 404

        org_id = suggestion.get("org_id", "default")

        # Create feedback
        fb_id = Feedback.create(
            suggestion_id=suggestion_id,
            vote=vote,
            user_id=user_id or "anonymous",
            comment=comment,
            org_id=org_id,
        )

        # Log to audit trail
        AuditLog.log(
            actor=f"user:{user_id}" if user_id else "system:anonymous",
            event_type="feedback_submitted",
            ref_id=suggestion_id,
            payload={"vote": vote, "comment": comment},
            org_id=org_id,
        )

        return jsonify({"id": fb_id, "status": "recorded"})
    except Exception as e:
        log.error(f"Error submitting feedback: {e}")
        return jsonify({"error": str(e)}), 400

@app.get("/api/feedback/stats")
@require_api_key
def api_feedback_stats():
    """Get feedback aggregation statistics (for learning)."""
    try:
        org_id = request.args.get("org_id", "default")
        period_days = int(request.args.get("period_days", 7))

        stats = Feedback.aggregate_by_type(org_id=org_id, period_days=period_days)

        return jsonify({
            "period_days": period_days,
            "org_id": org_id,
            "by_type": stats,
        })
    except Exception as e:
        log.error(f"Error getting feedback stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.post("/api/learning/jobs")
@require_api_key
def api_run_learning_job():
    """Trigger learning job manually."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        org_id = data.get("org_id", "default")

        result = run_learning_job(org_id=org_id)

        return jsonify(result)
    except Exception as e:
        log.error(f"Error running learning job: {e}")
        return jsonify({"error": str(e)}), 500

@app.get("/api/learning/stats")
@require_api_key
def api_learning_stats():
    """Get learning statistics and feedback aggregation."""
    try:
        org_id = request.args.get("org_id", "default")
        period_days = int(request.args.get("period_days", 7))

        stats = Feedback.aggregate_by_type(org_id=org_id, period_days=period_days)

        # Calculate overall metrics
        total_feedback = sum(s.get("total", 0) for s in stats.values())
        total_good = sum(s.get("good", 0) for s in stats.values())
        total_bad = sum(s.get("bad", 0) for s in stats.values())
        overall_good_ratio = total_good / total_feedback if total_feedback > 0 else 0.0

        return jsonify({
            "period_days": period_days,
            "org_id": org_id,
            "overall": {
                "total_feedback": total_feedback,
                "good": total_good,
                "bad": total_bad,
                "good_ratio": overall_good_ratio,
            },
            "by_type": stats,
        })
    except Exception as e:
        log.error(f"Error getting learning stats: {e}")
        return jsonify({"error": str(e)}), 500

# ── Agent Auth & Configuration ─────────────────────────────────────

def _get_agent_keys():
    """Parse RECO3_AGENT_KEYS env var.
    Supports CSV format: 'agent1=key1,agent2=key2'
    or JSON format: '{"agent1":"key1","agent2":"key2"}'
    """
    raw = os.getenv("RECO3_AGENT_KEYS", "").strip()
    if not raw:
        return {}
    # Try JSON first
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except Exception:
            pass
    # CSV format: agent_id=api_key,agent_id=api_key
    keys = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            aid, akey = pair.split("=", 1)
            keys[aid.strip()] = akey.strip()
    return keys

def _validate_agent_request():
    """Validate agent authentication from X-AGENT-ID + X-API-Key headers.
    Returns (agent_id, org_id) on success, or aborts with 401.
    """
    agent_id = request.headers.get("X-AGENT-ID", "").strip()
    api_key = request.headers.get("X-API-Key", "").strip()

    if not agent_id or not api_key:
        return None, None

    agent_keys = _get_agent_keys()
    expected = agent_keys.get(agent_id)
    if not expected or expected != api_key:
        return None, None

    return agent_id, "default"

def _is_test_mode():
    return os.getenv("RECO3_TEST_MODE", "0").strip() == "1"

def _require_approval():
    return os.getenv("RECO3_REQUIRE_APPROVAL", "1").strip() == "1"


# ── Agent API Endpoints ───────────────────────────────────────────

@app.post("/agent/heartbeat")
def agent_heartbeat():
    """Agent sends heartbeat with system metrics."""
    agent_id, org_id = _validate_agent_request()
    if not agent_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}

    AgentStatus.upsert(
        agent_id=agent_id,
        platform=data.get("platform", ""),
        version=data.get("version", "1.0"),
        payload=data.get("metrics", {}),
        org_id=org_id,
    )

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_heartbeat",
        ref_id=agent_id,
        payload={"platform": data.get("platform"), "version": data.get("version")},
        org_id=org_id,
    )

    return jsonify({"status": "ok"})


@app.post("/agent/logs")
def agent_logs_endpoint():
    """Agent sends log entries."""
    agent_id, org_id = _validate_agent_request()
    if not agent_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    logs_list = data.get("logs", [])

    count = AgentLogs.create_batch(agent_id, logs_list, org_id=org_id)

    # Auto-create incidents for ERROR/CRITICAL logs
    errors = [l for l in logs_list if l.get("level") in ("ERROR", "CRITICAL")]
    incident_ids = []
    for err in errors:
        inc_id = Incidents.create(
            severity="high" if err.get("level") == "CRITICAL" else "medium",
            title=f"Agent {agent_id}: {err.get('code', 'ERROR')}",
            summary=err.get("msg", ""),
            org_id=org_id,
        )
        incident_ids.append(inc_id)

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_logs",
        ref_id=agent_id,
        payload={"count": count, "errors": len(errors), "incidents": incident_ids},
        org_id=org_id,
    )

    return jsonify({"status": "ok", "count": count, "incidents_created": len(incident_ids)})


@app.get("/agent/pull")
def agent_pull():
    """Agent polls for pending commands."""
    agent_id, org_id = _validate_agent_request()
    if not agent_id:
        return jsonify({"error": "unauthorized"}), 401

    require_approval = _require_approval()
    pending = AgentCommands.list_pending(agent_id, require_approval=require_approval)

    # Mark as delivered
    for cmd in pending:
        AgentCommands.update_status(cmd["id"], "delivered")

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_pull",
        ref_id=agent_id,
        payload={"commands_delivered": len(pending)},
        org_id=org_id,
    )

    return jsonify({"commands": pending})


@app.post("/agent/report")
def agent_report():
    """Agent reports command execution result."""
    agent_id, org_id = _validate_agent_request()
    if not agent_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    cmd_id = data.get("command_id", "")
    result = data.get("result", {})
    cmd_status = data.get("status", "completed")

    if not cmd_id:
        return jsonify({"error": "missing command_id"}), 400

    cmd = AgentCommands.get_by_id(cmd_id)
    if not cmd or cmd["agent_id"] != agent_id:
        return jsonify({"error": "command_not_found"}), 404

    AgentCommands.update_status(cmd_id, cmd_status)
    AgentCommands.set_result(cmd_id, result)

    AuditLog.log(
        actor=f"agent:{agent_id}",
        event_type="agent_report",
        ref_id=cmd_id,
        payload={"status": cmd_status, "result": result},
        org_id=org_id,
    )

    return jsonify({"status": "ok"})


# ── Agent Management API (PWA-facing) ─────────────────────────────

@app.get("/api/agents")
@require_api_key
def api_list_agents():
    """List all agents with status."""
    try:
        org_id = request.args.get("org_id", "default")
        agents = AgentStatus.list_all(org_id=org_id)

        # Enrich with recent error count
        for agent in agents:
            recent_logs = AgentLogs.list_recent(
                agent_id=agent["agent_id"], level="ERROR", limit=10, org_id=org_id
            )
            agent["recent_error_count"] = len(recent_logs)
            agent["last_error"] = recent_logs[0]["msg"] if recent_logs else ""

        return jsonify({"agents": agents, "count": len(agents)})
    except Exception as e:
        log.error(f"Error listing agents: {e}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/agents/<agent_id>/logs")
@require_api_key
def api_agent_logs(agent_id):
    """Get recent logs for an agent."""
    try:
        org_id = request.args.get("org_id", "default")
        level = request.args.get("level")
        limit = int(request.args.get("limit", 50))
        logs_list = AgentLogs.list_recent(
            agent_id=agent_id, level=level, limit=limit, org_id=org_id
        )
        return jsonify({"logs": logs_list, "count": len(logs_list)})
    except Exception as e:
        log.error(f"Error getting agent logs: {e}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/agent-commands")
@require_api_key
def api_list_agent_commands():
    """List all agent commands (command queue)."""
    try:
        org_id = request.args.get("org_id", "default")
        agent_id = request.args.get("agent_id")
        limit = int(request.args.get("limit", 50))
        commands = AgentCommands.list_all(agent_id=agent_id, limit=limit, org_id=org_id)

        # Enrich with approval status
        for cmd in commands:
            if cmd["type"] in AgentCommands.STRONG_COMMANDS:
                approval = Approvals.get_for_command(cmd["id"])
                cmd["needs_approval"] = True
                cmd["approved"] = approval is not None
                cmd["approval"] = approval
            else:
                cmd["needs_approval"] = False
                cmd["approved"] = True
                cmd["approval"] = None

        return jsonify({"commands": commands, "count": len(commands)})
    except Exception as e:
        log.error(f"Error listing commands: {e}")
        return jsonify({"error": str(e)}), 500


@app.post("/api/agent-commands")
@require_api_key
def api_create_agent_command():
    """Create a command for an agent (from PWA/admin)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        agent_id = data.get("agent_id", "")
        cmd_type = data.get("type", "")
        payload = data.get("payload", {})
        org_id = data.get("org_id", "default")

        if not agent_id or not cmd_type:
            return jsonify({"error": "agent_id and type required"}), 400

        cmd_id = AgentCommands.create(
            agent_id=agent_id, cmd_type=cmd_type, payload=payload, org_id=org_id
        )

        AuditLog.log(
            actor="system:pwa",
            event_type="command_created",
            ref_id=cmd_id,
            payload={"agent_id": agent_id, "type": cmd_type, "payload": payload},
            org_id=org_id,
        )

        return jsonify({"id": cmd_id, "status": "created"})
    except Exception as e:
        log.error(f"Error creating command: {e}")
        return jsonify({"error": str(e)}), 400


@app.post("/api/agent-commands/<cmd_id>/approve")
@require_api_key
def api_approve_command(cmd_id):
    """Approve a strong command (RESTART, ROLLBACK, STOP)."""
    try:
        cmd = AgentCommands.get_by_id(cmd_id)
        if not cmd:
            return jsonify({"error": "command_not_found"}), 404

        if cmd["type"] not in AgentCommands.STRONG_COMMANDS:
            return jsonify({"error": "command does not require approval"}), 400

        existing = Approvals.get_for_command(cmd_id)
        if existing:
            return jsonify({"error": "already approved", "approval": existing}), 409

        data = request.get_json(force=True, silent=True) or {}
        approved_by = data.get("approved_by", "admin")
        org_id = cmd.get("org_id", "default")

        approval_id = Approvals.create(
            command_id=cmd_id, approved_by=approved_by, org_id=org_id
        )

        AuditLog.log(
            actor=f"user:{approved_by}",
            event_type="command_approved",
            ref_id=cmd_id,
            payload={"command_type": cmd["type"], "agent_id": cmd["agent_id"]},
            org_id=org_id,
        )

        return jsonify({"approval_id": approval_id, "status": "approved"})
    except Exception as e:
        log.error(f"Error approving command: {e}")
        return jsonify({"error": str(e)}), 400


@app.get("/api/r3/agents")
def api_r3_agents():
    """List agents for PWA (session auth)."""
    if not session.get("r3"):
        cfg = _get_api_key_config()
        if cfg["mode"] == "enforce":
            key = request.headers.get(cfg["header"], "").strip()
            if not key or key != cfg["api_key"]:
                return jsonify({"error": "unauthorized"}), 401
    try:
        org_id = request.args.get("org_id", "default")
        agents = AgentStatus.list_all(org_id=org_id)
        for agent in agents:
            recent_logs = AgentLogs.list_recent(
                agent_id=agent["agent_id"], level="ERROR", limit=10, org_id=org_id
            )
            agent["recent_error_count"] = len(recent_logs)
            agent["last_error"] = recent_logs[0]["msg"] if recent_logs else ""
        return jsonify({"agents": agents, "count": len(agents)})
    except Exception as e:
        log.error(f"Error listing agents: {e}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/r3/agent/<agent_id>/logs")
def api_r3_agent_logs(agent_id):
    """Get agent logs for PWA (session auth)."""
    if not session.get("r3"):
        cfg = _get_api_key_config()
        if cfg["mode"] == "enforce":
            key = request.headers.get(cfg["header"], "").strip()
            if not key or key != cfg["api_key"]:
                return jsonify({"error": "unauthorized"}), 401
    try:
        org_id = request.args.get("org_id", "default")
        limit = int(request.args.get("limit", 200))
        logs_list = AgentLogs.list_recent(agent_id=agent_id, limit=limit, org_id=org_id)
        return jsonify({"logs": logs_list, "count": len(logs_list)})
    except Exception as e:
        log.error(f"Error getting agent logs: {e}")
        return jsonify({"error": str(e)}), 500


@app.get("/api/config/test-mode")
def api_test_mode():
    """Get test mode and config status (no auth required for PWA)."""
    return jsonify({
        "test_mode": _is_test_mode(),
        "require_approval": _require_approval(),
    })


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
