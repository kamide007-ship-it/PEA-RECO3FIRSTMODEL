import importlib
from reco2 import engine

def test_evaluate_payload_basic(temp_instance):
    import reco2.store as store
    importlib.reload(store)
    importlib.reload(engine)
    res = engine.evaluate_payload({
        "inference": {"a": 0.7},
        "evidence": {"a": {"median": 0.6}},
        "context": {"domain": "general", "confidence": 0.7, "domain_known": True, "missing_fields": 0, "warnings": 0},
    })
    assert "session_id" in res and res["verdict"] in ("reliable", "moderate", "suspect")

def test_feedback_duplicate_ignored(temp_instance):
    importlib.reload(engine)
    ev = engine.evaluate_payload({
        "inference": {"a": 0.1},
        "evidence": {"a": {"median": 0.2}},
        "context": {"domain": "x", "confidence": 0.7},
    })
    sid = ev["session_id"]
    r1 = engine.record_feedback({"session_id": sid, "domain": "x", "feedback": "good"})
    assert r1["status"] == "recorded"
    r2 = engine.record_feedback({"session_id": sid, "domain": "x", "feedback": "bad"})
    assert r2["status"] == "duplicate_ignored"

def test_patrol_clamp(temp_instance):
    importlib.reload(engine)
    # create logs to force adjustments
    for _ in range(12):
        engine.evaluate_payload({
            "inference": {"a": 10.0},
            "evidence": {"a": {"median": 0.0}},
            "context": {"domain": "y", "confidence": 0.1, "domain_known": False, "warnings": 3},
        })
    st = engine.get_status()
    assert st["ranges"]["k"][0] <= st["k"] <= st["ranges"]["k"][1]
    assert st["ranges"]["eta"][0] <= st["eta"] <= st["ranges"]["eta"][1]
