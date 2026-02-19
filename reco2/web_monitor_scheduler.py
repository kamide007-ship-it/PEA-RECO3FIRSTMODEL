"""
Web monitoring scheduler: Periodic HTTP checks for monitored targets.
Creates observations and incidents from health check results.
"""

import requests
import logging
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from reco2.db import WebTargets, Observations, Incidents

logger = logging.getLogger(__name__)


class WebMonitorScheduler:
    """Periodic web monitoring scheduler."""

    def __init__(self, check_interval_sec: int = 60):
        """
        Initialize scheduler.

        Args:
            check_interval_sec: Main loop interval (will respect per-target interval_sec)
        """
        self.check_interval_sec = check_interval_sec
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Start monitoring scheduler in background thread."""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Web monitor scheduler started")

    def stop(self):
        """Stop monitoring scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Web monitor scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                self._check_all_targets()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

            time.sleep(self.check_interval_sec)

    def _check_all_targets(self):
        """Check all enabled web targets."""
        targets = WebTargets.list_enabled()
        for target in targets:
            try:
                self._check_target(target)
            except Exception as e:
                logger.error(f"Error checking target {target['id']}: {e}")

    def _check_target(self, target: Dict[str, Any]):
        """
        Check single web target and record observation.

        Args:
            target: Web target record from database
        """
        try:
            result = self._http_check(
                url=target["url"],
                method=target.get("method", "GET"),
                timeout_sec=5,
            )

            # Record observation
            obs_id = Observations.create(
                source_type="web",
                source_id=target["id"],
                kind="metric",
                payload={
                    "url": target["url"],
                    "status_code": result.get("status_code"),
                    "latency_ms": result.get("latency_ms"),
                    "body_length": result.get("body_length"),
                    "success": result.get("success"),
                    "error": result.get("error"),
                },
                org_id=target.get("org_id", "default"),
            )

            # Check if observation indicates anomaly
            self._check_and_create_incident(target, result, org_id=target.get("org_id", "default"))

        except Exception as e:
            logger.error(f"Error checking target {target['id']}: {e}")
            # Record failure observation
            Observations.create(
                source_type="web",
                source_id=target["id"],
                kind="metric",
                payload={
                    "url": target["url"],
                    "success": False,
                    "error": str(e),
                },
                org_id=target.get("org_id", "default"),
            )

    def _http_check(self, url: str, method: str = "GET", timeout_sec: int = 5) -> Dict[str, Any]:
        """
        Perform HTTP health check.

        Args:
            url: Target URL
            method: HTTP method (GET, POST, HEAD)
            timeout_sec: Request timeout

        Returns:
            Dictionary with check results: {status_code, latency_ms, body_length, success, error}
        """
        try:
            start = time.time()

            if method.upper() == "HEAD":
                resp = requests.head(url, timeout=timeout_sec, allow_redirects=True)
            elif method.upper() == "POST":
                resp = requests.post(url, timeout=timeout_sec, allow_redirects=True)
            else:
                resp = requests.get(url, timeout=timeout_sec, allow_redirects=True)

            elapsed_ms = int((time.time() - start) * 1000)

            return {
                "status_code": resp.status_code,
                "latency_ms": elapsed_ms,
                "body_length": len(resp.content),
                "success": 200 <= resp.status_code < 300,
                "error": None,
            }

        except requests.Timeout as e:
            return {
                "status_code": None,
                "latency_ms": int(timeout_sec * 1000),
                "body_length": 0,
                "success": False,
                "error": f"Timeout: {str(e)}",
            }
        except Exception as e:
            return {
                "status_code": None,
                "latency_ms": None,
                "body_length": 0,
                "success": False,
                "error": f"Error: {str(e)}",
            }

    def _check_and_create_incident(self, target: Dict, result: Dict, org_id: str = "default"):
        """
        Check if result indicates anomaly and create incident if needed.

        Args:
            target: Web target record
            result: HTTP check result
            org_id: Organization ID
        """
        expected_status = target.get("expected_status", 200)

        # Determine severity
        if not result.get("success"):
            status_code = result.get("status_code")
            if status_code and status_code >= 500:
                severity = "high"
                title = f"HTTP {status_code} on {target['name']}"
            elif result.get("error"):
                severity = "medium"
                title = f"Connection error on {target['name']}: {result['error'][:50]}"
            else:
                severity = "low"
                title = f"Status check failed on {target['name']}"

            # Create incident
            Incidents.create(
                severity=severity,
                title=title,
                summary=f"Target {target['url']} returned {result.get('status_code', 'unknown')}",
                org_id=org_id,
            )

        # Also check latency threshold
        latency_ms = result.get("latency_ms")
        expected_latency = target.get("expected_latency_ms", 1000)
        if latency_ms and latency_ms > expected_latency * 1.5:
            Incidents.create(
                severity="low",
                title=f"High latency on {target['name']}: {latency_ms}ms",
                summary=f"Expected < {expected_latency}ms",
                org_id=org_id,
            )


# Global scheduler instance
_scheduler: Optional[WebMonitorScheduler] = None


def get_scheduler() -> WebMonitorScheduler:
    """Get or create global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = WebMonitorScheduler(check_interval_sec=30)
        _scheduler.start()
    return _scheduler


def start_monitoring():
    """Start web monitoring."""
    get_scheduler()


def stop_monitoring():
    """Stop web monitoring."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None
