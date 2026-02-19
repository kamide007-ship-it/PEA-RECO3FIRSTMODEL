"""RECO3 PC Agent - Main Agent Loop.
Runs as a daemon/service, sends heartbeat/logs, polls for commands.
"""

import logging
import signal
import sys
import time
import os

# Add common directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from util import load_config, setup_logging
from http_client import RECOHttpClient
from metrics import collect_metrics
from logs_tail import LogTail
from commands import execute_command
from security import validate_command, is_strong_command

logger = logging.getLogger("reco3_agent")

# Consecutive failure threshold for SAFE mode
SAFE_MODE_FAILURE_THRESHOLD = 5


class RECOAgent:
    """Main RECO3 PC Agent."""

    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        setup_logging(self.config)

        self.agent_id = self.config["agent_id"]
        self.running = False
        self.current_mode = "NORMAL"

        self.client = RECOHttpClient(
            base_url=self.config["base_url"],
            agent_id=self.agent_id,
            api_key=self.config["api_key"],
        )

        watch_files = self.config.get("watch", {}).get("log_files", [])
        self.log_tail = LogTail(watch_files)
        self.log_buffer = []

        logger.info(f"Agent initialized: {self.agent_id} -> {self.config['base_url']}")
        logger.info(f"  Platform: {self.config['platform']}")
        logger.info(f"  apply_enabled: {self.config['control']['apply_enabled']}")

    def run(self):
        """Main agent loop."""
        self.running = True

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        hb_interval = self.config["intervals"]["heartbeat_sec"]
        pull_interval = self.config["intervals"]["pull_sec"]
        logs_interval = self.config["intervals"]["logs_sec"]

        last_hb = 0
        last_pull = 0
        last_logs = 0

        logger.info(f"Agent loop started (hb={hb_interval}s, pull={pull_interval}s, logs={logs_interval}s)")

        while self.running:
            now = time.time()

            # 1. Heartbeat
            if now - last_hb >= hb_interval:
                self._send_heartbeat()
                last_hb = now

            # 2. Collect log entries
            if now - last_logs >= logs_interval:
                self._collect_logs()
                last_logs = now

            # 3. Send buffered logs
            if self.log_buffer:
                self._send_logs()

            # 4. Pull and execute commands
            if now - last_pull >= pull_interval:
                self._pull_and_execute()
                last_pull = now

            # 5. Check for safe mode due to communication failures
            if self.client.consecutive_failures >= SAFE_MODE_FAILURE_THRESHOLD:
                if self.current_mode != "SAFE":
                    logger.warning(f"Entering SAFE mode ({self.client.consecutive_failures} failures)")
                    self.current_mode = "SAFE"

            time.sleep(1)

        logger.info("Agent loop ended")

    def stop(self):
        """Graceful shutdown."""
        logger.info("Stopping agent...")
        self.running = False

        # Send remaining logs
        if self.log_buffer:
            try:
                self._send_logs()
            except Exception:
                pass

    def _signal_handler(self, signum, frame):
        """Handle OS signals for graceful shutdown."""
        logger.info(f"Signal received: {signum}")
        self.stop()

    def _send_heartbeat(self):
        """Send heartbeat with system metrics."""
        try:
            metrics = collect_metrics(self.config)
            metrics["mode"] = self.current_mode
            payload = {
                "platform": self.config["platform"],
                "version": self.config["version"],
                "metrics": metrics,
            }
            self.client.post("/agent/heartbeat", payload)
            logger.debug("Heartbeat sent")
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")

    def _collect_logs(self):
        """Collect new log entries from monitored files."""
        try:
            new_entries = self.log_tail.get_new_entries()
            self.log_buffer.extend(new_entries)
            if new_entries:
                logger.info(f"Collected {len(new_entries)} log entries")
        except Exception as e:
            logger.error(f"Log collection error: {e}")

    def _send_logs(self):
        """Send buffered logs to server."""
        try:
            batch = self.log_buffer[:100]  # Max 100 per batch
            self.client.post("/agent/logs", {"logs": batch})
            self.log_buffer = self.log_buffer[100:]
            logger.debug(f"Sent {len(batch)} log entries")
        except Exception as e:
            logger.error(f"Log send failed: {e}")

    def _pull_and_execute(self):
        """Pull commands from server and execute."""
        try:
            response = self.client.get("/agent/pull")
            commands = response.get("commands", [])

            for cmd in commands:
                self._execute_single(cmd)
        except Exception as e:
            logger.error(f"Pull failed: {e}")

    def _execute_single(self, cmd: dict):
        """Execute a single command with security checks."""
        cmd_id = cmd.get("id", "")
        cmd_type = cmd.get("type", "")
        payload = cmd.get("payload_json", "{}")

        # Parse payload if string
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}

        logger.info(f"Executing command: {cmd_type} (id={cmd_id})")

        # 1. Security validation (allowlist)
        valid, reason = validate_command(cmd_type, payload, self.config)
        if not valid:
            logger.warning(f"Command rejected: {reason}")
            self._report_result(cmd_id, "failed", {"success": False, "error": reason})
            return

        # 2. Dual-lock check for strong commands
        if is_strong_command(cmd_type):
            apply_enabled = self.config.get("control", {}).get("apply_enabled", False)
            if not apply_enabled:
                msg = f"Strong command '{cmd_type}' blocked: apply_enabled=false"
                logger.warning(msg)
                self._report_result(cmd_id, "failed", {"success": False, "error": msg})
                return

        # 3. Execute
        try:
            result = execute_command(cmd_type, payload, self.config)
            status = "completed" if result.get("success") else "failed"
            self._report_result(cmd_id, status, result)

            # Update mode if SET_MODE
            if cmd_type == "SET_MODE" and result.get("success"):
                self.current_mode = result.get("mode", self.current_mode)
                logger.info(f"Mode changed to: {self.current_mode}")

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            self._report_result(cmd_id, "failed", {"success": False, "error": str(e)})

    def _report_result(self, cmd_id: str, status: str, result: dict):
        """Report command result to server."""
        try:
            self.client.post("/agent/report", {
                "command_id": cmd_id,
                "status": status,
                "result": result,
            })
        except Exception as e:
            logger.error(f"Report failed: {e}")


def main():
    """Entry point."""
    config_path = "config.yaml"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    agent = RECOAgent(config_path)
    agent.run()


if __name__ == "__main__":
    main()
