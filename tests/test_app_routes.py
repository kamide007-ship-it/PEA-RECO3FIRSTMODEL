import importlib
import json
import pytest

def test_dashboards(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    assert c.get("/").status_code == 200
    assert c.get("/r3").status_code == 200

def test_status(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.get("/api/status")
    assert r.status_code == 200
    j = r.get_json()
    assert "k" in j and "total_sessions" in j

def test_logs(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.get("/api/logs?limit=5")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

def test_evaluate(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    payload = {"inference":{"a":0.1},"evidence":{"a":{"median":0.2}},"context":{"domain":"general","confidence":0.7}}
    r = c.post("/api/evaluate", json=payload)
    assert r.status_code == 200 and "session_id" in r.get_json()

def test_feedback_route(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    payload = {"inference":{"a":0.1},"evidence":{"a":{"median":0.2}},"context":{"domain":"general","confidence":0.7}}
    ev = c.post("/api/evaluate", json=payload).get_json()
    sid = ev["session_id"]
    r = c.post("/api/feedback", json={"session_id": sid, "domain":"general", "feedback":"good"})
    assert r.status_code == 200 and r.get_json()["status"] in ("recorded","duplicate_ignored")

def test_r3_analyze_input(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.post("/api/r3/analyze_input", json={"text":"今すぐ！"})
    assert r.status_code == 200 and "risk_level" in r.get_json()

def test_r3_analyze_output(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.post("/api/r3/analyze_output", json={"text":"必ず成功。"})
    assert r.status_code == 200 and "psi_modifier" in r.get_json()

def test_health(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"

def test_r3_chat(temp_instance):
    import app as appmod
    importlib.reload(appmod)
    c = appmod.app.test_client()
    r = c.post("/api/r3/chat", json={"prompt":"こんにちは","domain":"general"})
    assert r.status_code == 200
    j = r.get_json()
    assert "response" in j and "input_analysis" in j
