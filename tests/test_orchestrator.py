import importlib
from reco2.orchestrator import Orchestrator
from reco2.llm_adapter import DummyAdapter

def test_process_low_risk(temp_instance):
    orch = Orchestrator(DummyAdapter("ok"))
    res = orch.process("普通の質問", domain="general", context={"confidence": 0.7})
    assert "response" in res and res["session_id"]

def test_process_critical_cooldown(temp_instance):
    orch = Orchestrator(DummyAdapter("ok"))
    res = orch.process("今すぐ！完璧に！絶対に！", domain="general")
    assert res["session_id"] is None and "冷却モード" in res["response"]

def test_degraded_output_soften(temp_instance):
    orch = Orchestrator(DummyAdapter("必ず成功します。絶対に。"))
    res = orch.process("Q", domain="general")
    assert "多くの場合" in res["response"] or "ほぼ" in res["response"]

def test_llm_swap(temp_instance):
    orch = Orchestrator(DummyAdapter("a"))
    orch.set_llm(DummyAdapter("b"))
    res = orch.process("Q", domain="general")
    assert res["response"] == "b"

def test_reco2_bridge(temp_instance):
    orch = Orchestrator(DummyAdapter("ok"))
    res = orch.process("Q", domain="general", context={"confidence": 0.7})
    assert res["reco2_evaluation"]["session_id"] == res["session_id"]
