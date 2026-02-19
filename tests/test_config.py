import importlib
from reco2 import config

def test_defaults_exist(temp_instance):
    importlib.reload(config)
    cfg = config.load_config()
    assert cfg["port"] == 5001 and cfg["llm_adapter"] == "auto"

def test_public_masks(temp_instance):
    cfg = config.load_config()
    cfg["api_keys"] = ["a","b"]
    pub = config.public_config(cfg)
    assert pub["api_keys"] == ["***","***"]

def test_api_key_disabled_default(temp_instance):
    cfg = config.load_config()
    assert cfg["api_key_enabled"] is False
