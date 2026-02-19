from reco2 import output_gate

def test_healthy_short():
    a = output_gate.analyze("これは短い説明です。")
    assert a["level"] == "healthy"

def test_assertion_heavy():
    a = output_gate.analyze("必ず成功します。絶対に大丈夫。100%です。")
    assert a["scores"]["assertion_density"] > 0

def test_contradiction_pair():
    a = output_gate.analyze("必ずいけます。でも、かもしれません。")
    assert a["counts"]["contradictions"] >= 1

def test_provocative():
    a = output_gate.analyze("使えない。")
    assert a["scores"]["provocative"] > 0

def test_psi_modifier_range():
    a = output_gate.analyze("必ず成功します。絶対。")
    assert 0.3 <= a["psi_modifier"] <= 1.0

def test_soften_ja():
    t = output_gate.soften("必ず大丈夫。絶対に。")
    assert "多くの場合" in t or "ほぼ" in t

def test_soften_en():
    t = output_gate.soften("This will definitely work and always succeed.")
    assert "likely" in t.lower() or "typically" in t.lower()
