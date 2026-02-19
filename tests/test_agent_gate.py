import importlib
from unittest.mock import patch

def test_safe_input_no_rewrite():
    import reco3_agent.agent_gate as g
    res = g.evaluate_input("こんにちは", {"session_history": [], "daily_counts": {}}, "http://127.0.0.1:5001")
    assert res["action"] in ("pass", "warn")  # fatigue alone should not block
    if res["action"] == "pass":
        assert not res["rewrite"]

def test_emotional_rewrite_local():
    import reco3_agent.agent_gate as g
    res = g.evaluate_input("今すぐ！使えない！", {"session_history": [], "daily_counts": {}}, "")
    assert res["rewrite"] is True and res["text"].startswith("[冷静モード")

def test_worst_of_merge_remote(monkeypatch):
    import reco3_agent.agent_gate as g
    def fake_post(url, payload, timeout=5):
        return {"risk_level": "critical", "temperature_modifier": 0.3}
    monkeypatch.setattr(g, "_post_json", fake_post)
    res = g.evaluate_input("こんにちは", {"session_history": [], "daily_counts": {}}, "http://x")
    assert res["action"] == "cool"

def test_output_eval_logs(monkeypatch):
    import reco3_agent.agent_gate as g
    monkeypatch.setattr(g, "_post_json", lambda url, payload, timeout=5: {"level":"healthy"})
    r = g.evaluate_output("ok", "http://x")
    assert r["remote"]["level"] == "healthy"
