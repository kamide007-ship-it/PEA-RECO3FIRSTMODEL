import importlib
import time

def _state():
    return {"session_history": [], "daily_counts": {}, "total_sessions": 0}

def test_emotional_score():
    from reco3_agent.analyzer import score_emotional
    assert score_emotional("今すぐ！！") > 0

def test_overload_score():
    from reco3_agent.analyzer import score_overload
    assert score_overload("全部やって") > 0

def test_fatigue_burst():
    from reco3_agent.analyzer import score_fatigue
    st = _state()
    now = time.time()
    st["session_history"] = [now - 10] * 25
    assert score_fatigue(st) > 0.7

def test_fatigue_daily():
    from reco3_agent.analyzer import score_fatigue
    import datetime
    st = _state()
    day = datetime.date.today().isoformat()
    st["daily_counts"] = {day: 60}
    assert score_fatigue(st) > 0.8

def test_analyze_pass():
    from reco3_agent.analyzer import analyze_human
    res = analyze_human("こんにちは", _state())
    assert res["action"] in ("pass", "warn")  # fatigue (night hours) may promote to warn

def test_analyze_warn():
    from reco3_agent.analyzer import analyze_human
    res = analyze_human("急いで！", _state())
    assert res["action"] in ("warn","block","cool")

def test_composite_calc():
    from reco3_agent.analyzer import analyze_human
    res = analyze_human("全部！今すぐ！", _state())
    assert 0.0 <= res["composite"] <= 1.0

def test_analyze_human_calm():
    """Calm text at night should not be blocked — fatigue alone only promotes to warn."""
    from reco3_agent.analyzer import analyze_human
    res = analyze_human("こんにちは、元気ですか？", _state())
    assert res["action"] in ("pass", "warn")
    assert res["temperature_modifier"] >= 0.8

def test_temperature_modifier_bounds():
    from reco3_agent.analyzer import analyze_human
    res = analyze_human("今すぐ！", _state())
    assert res["temperature_modifier"] in (0.3, 0.4, 0.7, 0.85, 1.0)
