from reco2 import input_gate

def test_low_risk():
    a = input_gate.analyze("今日の天気は？")
    assert a["risk_level"] == "low"

def test_ambiguity():
    a = input_gate.analyze("なんとなくいい感じにして")
    assert a["scores"]["ambiguity"] > 0

def test_assertion():
    a = input_gate.analyze("絶対に100%で断言して")
    assert a["scores"]["assertion_demand"] > 0

def test_emotion():
    a = input_gate.analyze("今すぐ！早く！使えない！")
    assert a["scores"]["emotional_pressure"] > 0

def test_unrealistic():
    a = input_gate.analyze("完璧にバグのない万能な答えを")
    assert a["scores"]["unrealistic"] > 0

def test_critical_level():
    a = input_gate.analyze("今すぐ！絶対に！完璧に！使えない！")
    assert a["risk_level"] in ("high","critical")

def test_rebuild_low():
    a = input_gate.analyze("普通の質問")
    p, mode = input_gate.rebuild_prompt("普通の質問", a)
    assert mode == "none" and p == "普通の質問"

def test_rebuild_moderate_prefix():
    a = {"risk_level": "moderate"}
    p, mode = input_gate.rebuild_prompt("Q", a)
    assert mode == "moderate" and p.startswith("[指針:")

def test_rebuild_critical_empty():
    a = {"risk_level": "critical"}
    p, mode = input_gate.rebuild_prompt("Q", a)
    assert mode == "critical" and p == ""
