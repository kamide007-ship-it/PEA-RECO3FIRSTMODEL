"""Command validation and security for RECO3 PC Agent.
Implements allowlist-based command filtering and dual-lock enforcement.
"""

import logging

logger = logging.getLogger(__name__)

# Allowed command types and their validation rules
ALLOWED_COMMANDS = {
    "SET_MODE": {
        "requires_approval": False,
        "requires_apply_enabled": False,
        "params": ["mode"],
        "allowed_values": {"mode": ["NORMAL", "SAFE", "LOCKED"]},
    },
    "SET_RATE_LIMIT": {
        "requires_approval": False,
        "requires_apply_enabled": True,
        "params": ["endpoint", "limit_rps"],
    },
    "NOTIFY_OPS": {
        "requires_approval": False,
        "requires_apply_enabled": False,
        "params": ["severity", "message"],
    },
    "RESTART_PROCESS": {
        "requires_approval": True,
        "requires_apply_enabled": True,
        "params": ["process"],
    },
    "STOP_PROCESS": {
        "requires_approval": True,
        "requires_apply_enabled": True,
        "params": ["process"],
    },
    "ROLLBACK": {
        "requires_approval": True,
        "requires_apply_enabled": True,
        "params": [],
    },
}

# Strong commands that need dual-lock (server approval + agent apply_enabled)
STRONG_COMMANDS = {"RESTART_PROCESS", "STOP_PROCESS", "ROLLBACK"}


def validate_command(cmd_type: str, payload: dict, config: dict) -> tuple:
    """Validate a command against the allowlist and dual-lock rules.

    Returns:
        (valid: bool, reason: str)
    """
    # 1. Check allowlist
    if cmd_type not in ALLOWED_COMMANDS:
        return False, f"Command '{cmd_type}' not in allowlist"

    spec = ALLOWED_COMMANDS[cmd_type]

    # 2. Check if apply_enabled is required and set
    if spec.get("requires_apply_enabled", False):
        apply_enabled = config.get("control", {}).get("apply_enabled", False)
        if not apply_enabled:
            return False, f"Command '{cmd_type}' requires control.apply_enabled=true"

    # 3. Validate allowed values
    allowed_vals = spec.get("allowed_values", {})
    for param, valid_values in allowed_vals.items():
        val = payload.get(param)
        if val and val not in valid_values:
            return False, f"Invalid value '{val}' for param '{param}'. Allowed: {valid_values}"

    # 4. SET_MODE: Check safe modes
    if cmd_type == "SET_MODE":
        mode = payload.get("mode", "")
        safe_modes = config.get("control", {}).get("safe_modes", ["NORMAL", "SAFE"])
        if mode not in safe_modes and mode not in ["LOCKED"]:
            return False, f"Mode '{mode}' not in safe_modes: {safe_modes}"

    # 5. Strong commands: Log extra warning
    if cmd_type in STRONG_COMMANDS:
        logger.warning(f"STRONG COMMAND validated: {cmd_type} payload={payload}")

    return True, "OK"


def is_strong_command(cmd_type: str) -> bool:
    """Check if a command type is a strong (dangerous) command."""
    return cmd_type in STRONG_COMMANDS
