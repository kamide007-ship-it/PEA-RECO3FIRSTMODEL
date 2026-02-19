"""
SQLite database management for RECO3 observations, incidents, suggestions, feedback, and audit logging.
Provides ORM-like access to observations, incidents, suggestions, feedback, learn_rules, web_targets, agent_status, and audit_log tables.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import uuid

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("RECO3_DB_PATH", "instance/reco3.db")


def get_db_path() -> str:
    """Get database file path, ensuring directory exists."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return DB_PATH


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row  # Return rows as dicts
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # observations: Time-series monitoring data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                ts DATETIME NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_obs_ts_source ON observations(ts, source_type)"
        )

        # incidents: Anomalies and issues
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                ts_open DATETIME NOT NULL,
                ts_close DATETIME,
                severity TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                status TEXT NOT NULL,
                root_cause TEXT,
                observation_ids TEXT,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_inc_ts_status ON incidents(ts_open, status)"
        )

        # suggestions: Proposed actions/solutions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                ts DATETIME NOT NULL,
                suggestion_type TEXT,
                action_json TEXT,
                rationale TEXT,
                confidence REAL,
                status TEXT NOT NULL,
                priority INT DEFAULT 0,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(incident_id) REFERENCES incidents(id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sug_incident ON suggestions(incident_id, status)"
        )

        # feedback: User evaluations of suggestions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id TEXT PRIMARY KEY,
                suggestion_id TEXT NOT NULL,
                user_id TEXT,
                vote TEXT NOT NULL,
                comment TEXT,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(suggestion_id) REFERENCES suggestions(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fb_suggestion ON feedback(suggestion_id)")

        # learn_rules: Learning rules and thresholds
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learn_rules (
                id TEXT PRIMARY KEY,
                rule_key TEXT UNIQUE NOT NULL,
                enabled BOOLEAN DEFAULT TRUE,
                threshold_json TEXT,
                version INT DEFAULT 1,
                updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                org_id TEXT DEFAULT 'default'
            )
        """)

        # models: ML model artifacts and metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version INT NOT NULL,
                artifact_path TEXT,
                updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                org_id TEXT DEFAULT 'default'
            )
        """)

        # web_targets: Web monitoring targets
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS web_targets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                method TEXT DEFAULT 'GET',
                interval_sec INT DEFAULT 300,
                expected_status INT DEFAULT 200,
                expected_latency_ms INT DEFAULT 1000,
                enabled BOOLEAN DEFAULT TRUE,
                tags TEXT,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # agent_status: PC agent heartbeat and metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_status (
                agent_id TEXT PRIMARY KEY,
                last_seen DATETIME NOT NULL,
                payload_json TEXT,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # audit_log: Comprehensive audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                ts DATETIME NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ref_id TEXT,
                payload_json TEXT,
                org_id TEXT DEFAULT 'default',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)")

        conn.commit()
        logger.info(f"Database initialized at {get_db_path()}")


class Observations:
    """observations table operations."""

    @staticmethod
    def create(
        source_type: str,
        source_id: str,
        kind: str,
        payload: Dict[str, Any],
        org_id: str = "default",
    ) -> str:
        """Create observation record."""
        obs_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO observations (id, ts, source_type, source_id, kind, payload_json, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (obs_id, ts, source_type, source_id, kind, json.dumps(payload), org_id),
            )
        logger.info(f"Created observation {obs_id}")
        return obs_id

    @staticmethod
    def list_recent(source_type: str = None, limit: int = 100, org_id: str = "default") -> List[Dict]:
        """List recent observations."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if source_type:
                cursor.execute(
                    """
                    SELECT * FROM observations
                    WHERE source_type = ? AND org_id = ?
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (source_type, org_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM observations
                    WHERE org_id = ?
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (org_id, limit),
                )
            return [dict(row) for row in cursor.fetchall()]


class Incidents:
    """incidents table operations."""

    @staticmethod
    def create(
        severity: str,
        title: str,
        summary: str = None,
        observation_ids: List[str] = None,
        org_id: str = "default",
    ) -> str:
        """Create incident."""
        incident_id = str(uuid.uuid4())
        ts_open = datetime.utcnow().isoformat() + "Z"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO incidents (id, ts_open, severity, title, summary, status, observation_ids, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    ts_open,
                    severity,
                    title,
                    summary,
                    "open",
                    json.dumps(observation_ids or []),
                    org_id,
                ),
            )
        logger.info(f"Created incident {incident_id}: {title}")
        return incident_id

    @staticmethod
    def list_by_status(status: str, org_id: str = "default", limit: int = 50) -> List[Dict]:
        """List incidents by status."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM incidents
                WHERE status = ? AND org_id = ?
                ORDER BY ts_open DESC LIMIT ?
                """,
                (status, org_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(incident_id: str) -> Optional[Dict]:
        """Get incident by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_status(incident_id: str, new_status: str, root_cause: str = None):
        """Update incident status."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if new_status == "closed":
                ts_close = datetime.utcnow().isoformat() + "Z"
                cursor.execute(
                    "UPDATE incidents SET status = ?, root_cause = ?, ts_close = ? WHERE id = ?",
                    (new_status, root_cause, ts_close, incident_id),
                )
            else:
                cursor.execute(
                    "UPDATE incidents SET status = ?, root_cause = ? WHERE id = ?",
                    (new_status, root_cause, incident_id),
                )


class Suggestions:
    """suggestions table operations."""

    @staticmethod
    def create(
        incident_id: str,
        suggestion_type: str,
        rationale: str,
        confidence: float = 0.5,
        action: Dict = None,
        org_id: str = "default",
    ) -> str:
        """Create suggestion."""
        sug_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO suggestions (id, incident_id, ts, suggestion_type, action_json, rationale, confidence, status, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sug_id,
                    incident_id,
                    ts,
                    suggestion_type,
                    json.dumps(action or {}),
                    rationale,
                    confidence,
                    "pending",
                    org_id,
                ),
            )
        logger.info(f"Created suggestion {sug_id} for incident {incident_id}")
        return sug_id

    @staticmethod
    def list_by_incident(incident_id: str, org_id: str = "default") -> List[Dict]:
        """List suggestions for incident."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM suggestions
                WHERE incident_id = ? AND org_id = ?
                ORDER BY priority DESC, ts DESC
                """,
                (incident_id, org_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(suggestion_id: str) -> Optional[Dict]:
        """Get suggestion by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_status(suggestion_id: str, new_status: str):
        """Update suggestion status."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE suggestions SET status = ? WHERE id = ?", (new_status, suggestion_id)
            )

    @staticmethod
    def update_priority(suggestion_id: str, new_priority: int):
        """Update suggestion priority (used by learning job)."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE suggestions SET priority = ? WHERE id = ?",
                (new_priority, suggestion_id),
            )


class Feedback:
    """feedback table operations."""

    @staticmethod
    def create(suggestion_id: str, vote: str, user_id: str = None, comment: str = None, org_id: str = "default") -> str:
        """Create feedback."""
        fb_id = str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO feedback (id, suggestion_id, user_id, vote, comment, org_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (fb_id, suggestion_id, user_id, vote, comment, org_id),
            )
        logger.info(f"Created feedback {fb_id}: {vote} on suggestion {suggestion_id}")
        return fb_id

    @staticmethod
    def list_by_suggestion(suggestion_id: str) -> List[Dict]:
        """List feedback for suggestion."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM feedback WHERE suggestion_id = ? ORDER BY created_at DESC",
                (suggestion_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def aggregate_by_type(org_id: str = "default", period_days: int = 7) -> Dict:
        """Aggregate feedback by suggestion type (for learning)."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT s.suggestion_type, f.vote, COUNT(*) as count
                FROM feedback f
                JOIN suggestions s ON f.suggestion_id = s.id
                WHERE f.org_id = ? AND f.created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY s.suggestion_type, f.vote
                """,
                (org_id, period_days),
            )
            rows = cursor.fetchall()

            agg = {}
            for row in rows:
                sug_type = row[0]
                vote = row[1]
                count = row[2]
                if sug_type not in agg:
                    agg[sug_type] = {"good": 0, "bad": 0, "total": 0}
                agg[sug_type][vote] += count
                agg[sug_type]["total"] += count

            for sug_type in agg:
                agg[sug_type]["good_ratio"] = (
                    agg[sug_type]["good"] / agg[sug_type]["total"]
                    if agg[sug_type]["total"] > 0
                    else 0.0
                )

            return agg


class WebTargets:
    """web_targets table operations."""

    @staticmethod
    def create(
        name: str,
        url: str,
        method: str = "GET",
        interval_sec: int = 300,
        expected_status: int = 200,
        expected_latency_ms: int = 1000,
        tags: List[str] = None,
        org_id: str = "default",
    ) -> str:
        """Create web monitoring target."""
        target_id = str(uuid.uuid4())

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO web_targets (id, name, url, method, interval_sec, expected_status, expected_latency_ms, tags, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    name,
                    url,
                    method,
                    interval_sec,
                    expected_status,
                    expected_latency_ms,
                    json.dumps(tags or []),
                    org_id,
                ),
            )
        logger.info(f"Created web target {target_id}: {name} -> {url}")
        return target_id

    @staticmethod
    def list_enabled(org_id: str = "default") -> List[Dict]:
        """List enabled web targets."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM web_targets
                WHERE enabled = TRUE AND org_id = ?
                ORDER BY name
                """,
                (org_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_by_id(target_id: str) -> Optional[Dict]:
        """Get web target by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM web_targets WHERE id = ?", (target_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def delete(target_id: str):
        """Delete web target."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM web_targets WHERE id = ?", (target_id,))


class AuditLog:
    """audit_log table operations."""

    @staticmethod
    def log(
        actor: str,
        event_type: str,
        ref_id: str = None,
        payload: Dict = None,
        org_id: str = "default",
    ) -> str:
        """Create audit log entry."""
        log_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat() + "Z"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log (id, ts, actor, event_type, ref_id, payload_json, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, ts, actor, event_type, ref_id, json.dumps(payload or {}), org_id),
            )
        return log_id

    @staticmethod
    def list_recent(org_id: str = "default", limit: int = 100) -> List[Dict]:
        """List recent audit log entries."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM audit_log
                WHERE org_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (org_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
