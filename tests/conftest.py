import os
import sys
from pathlib import Path
import pytest

# Ensure repo root is importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

@pytest.fixture()
def temp_instance(tmp_path, monkeypatch):
    """Provide an isolated instance/ and HOME for tests."""
    inst = tmp_path / "instance"
    inst.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("RECO3_INSTANCE_DIR", str(inst))

    # Isolate HOME for reco3_agent (~/.reco3)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))

    return inst
