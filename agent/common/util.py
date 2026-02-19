"""Shared utilities for RECO3 PC Agent."""

import os
import sys
import logging
import yaml


def load_config(config_path: str) -> dict:
    """Load YAML configuration file."""
    if not os.path.exists(config_path):
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Defaults
    cfg.setdefault("base_url", "http://127.0.0.1:5001")
    cfg.setdefault("agent_id", "agent-default")
    cfg.setdefault("api_key", "")
    cfg.setdefault("platform", sys.platform)
    cfg.setdefault("version", "1.0")
    cfg.setdefault("control", {})
    cfg["control"].setdefault("apply_enabled", False)
    cfg["control"].setdefault("safe_modes", ["NORMAL", "SAFE"])
    cfg.setdefault("watch", {})
    cfg["watch"].setdefault("processes", [])
    cfg["watch"].setdefault("log_files", [])
    cfg.setdefault("intervals", {})
    cfg["intervals"].setdefault("heartbeat_sec", 10)
    cfg["intervals"].setdefault("pull_sec", 10)
    cfg["intervals"].setdefault("logs_sec", 15)
    cfg.setdefault("logging", {})
    cfg["logging"].setdefault("level", "INFO")
    cfg["logging"].setdefault("file", "")

    return cfg


def setup_logging(cfg: dict):
    """Setup logging from config."""
    log_cfg = cfg.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

    handlers = [logging.StreamHandler(sys.stdout)]
    log_file = log_cfg.get("file", "")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
