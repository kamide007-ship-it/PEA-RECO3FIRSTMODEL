import os
import json
import importlib
from pathlib import Path

def test_default_roundtrip(tmp_path, monkeypatch):
    # redirect HOME for agent
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    import reco3_agent.state as st
    importlib.reload(st)
    s = st.load_state()
    assert s["user_id"] == "default"
    s["user_id"] = "u1"
    st.save_state(s)
    s2 = st.load_state()
    assert s2["user_id"] == "u1"

def test_record_session(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    import reco3_agent.state as st
    importlib.reload(st)
    s = st.load_state()
    s = st.record_session(s)
    assert s["total_sessions"] == 1 and len(s["session_history"]) == 1

def test_domain_weight(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    import reco3_agent.state as st
    importlib.reload(st)
    s = st.load_state()
    assert st.get_domain_weight(s, "x") == 1.0
    s = st.update_domain_weight(s, "x", 1.2)
    assert st.get_domain_weight(s, "x") == 1.2

def test_append_and_read_logs(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    import reco3_agent.state as st
    importlib.reload(st)
    st.append_log({"a": 1})
    logs = st.read_logs(limit=10)
    assert logs and logs[-1]["a"] == 1

def test_reset_state(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    import reco3_agent.state as st
    importlib.reload(st)
    s = st.load_state()
    s["user_id"] = "x"
    st.save_state(s)
    st.reset_state()
    s2 = st.load_state()
    assert s2["user_id"] == "default"
