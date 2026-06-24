import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "audit.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the runs table if it does not already exist."""
    try:
        with _get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id              TEXT PRIMARY KEY,
                    incident_id         TEXT NOT NULL,
                    started_at          TEXT NOT NULL,
                    completed_at        TEXT,
                    status              TEXT NOT NULL DEFAULT 'running',
                    severity            TEXT,
                    affected_systems    TEXT,
                    triage_notes        TEXT,
                    root_cause          TEXT,
                    rca_summary         TEXT,
                    recommended_fix     TEXT,
                    approved            INTEGER,
                    approver            TEXT,
                    approval_notes      TEXT,
                    email_sent          INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()
    except Exception as exc:
        logger.warning("audit init_db failed: %s", exc)


def record_run_started(run_id: str, incident_id: str, state: dict) -> None:
    """Insert a new run row right after the initial graph invoke completes
    (triage + RCA are done, workflow is now blocked at the approval interrupt)."""
    now = datetime.now(UTC).isoformat()
    affected = json.dumps(state.get("affected_systems") or [])
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, incident_id, started_at, status,
                    severity, affected_systems, triage_notes,
                    root_cause, rca_summary, recommended_fix, email_sent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    incident_id,
                    now,
                    "awaiting_approval",
                    state.get("severity"),
                    affected,
                    state.get("triage_notes"),
                    state.get("root_cause"),
                    state.get("rca_summary"),
                    state.get("recommended_fix"),
                    1 if state.get("email_sent") else 0,
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("audit record_run_started failed: %s", exc)


def record_run_completed(run_id: str, state: dict) -> None:
    """Update the run row after the approval step resolves."""
    now = datetime.now(UTC).isoformat()
    approved = state.get("approved")
    status = "completed" if approved else "rejected"
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    completed_at    = ?,
                    status          = ?,
                    approved        = ?,
                    approver        = ?,
                    approval_notes  = ?,
                    email_sent      = ?,
                    severity        = COALESCE(?, severity),
                    root_cause      = COALESCE(?, root_cause),
                    rca_summary     = COALESCE(?, rca_summary),
                    recommended_fix = COALESCE(?, recommended_fix)
                WHERE run_id = ?
                """,
                (
                    now,
                    status,
                    1 if approved else 0,
                    state.get("approver"),
                    state.get("approval_notes"),
                    1 if state.get("email_sent") else 0,
                    state.get("severity"),
                    state.get("root_cause"),
                    state.get("rca_summary"),
                    state.get("recommended_fix"),
                    run_id,
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("audit record_run_completed failed: %s", exc)


def get_all_runs(limit: int = 100) -> list[dict]:
    """Return the most recent runs ordered by start time descending."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                r = dict(row)
                # Decode JSON-encoded list back to Python list
                try:
                    r["affected_systems"] = json.loads(r.get("affected_systems") or "[]")
                except Exception:
                    r["affected_systems"] = []
                result.append(r)
            return result
    except Exception as exc:
        logger.warning("audit get_all_runs failed: %s", exc)
        return []


def get_run(run_id: str) -> dict | None:
    """Return a single run by run_id, or None if not found."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            r = dict(row)
            try:
                r["affected_systems"] = json.loads(r.get("affected_systems") or "[]")
            except Exception:
                r["affected_systems"] = []
            return r
    except Exception as exc:
        logger.warning("audit get_run failed: %s", exc)
        return None
