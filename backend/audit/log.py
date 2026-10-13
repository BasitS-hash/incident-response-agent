import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from backend.audit.chain import (
    ChainVerification,
    append_entry,
    ensure_chain,
    verify_chain,
)

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "audit.db"

# Columns added after the table's first version, keyed by column name. Each
# statement is a literal, applied only when that column is absent.
_MIGRATIONS = {
    "input_guard_findings": "ALTER TABLE runs ADD COLUMN input_guard_findings TEXT",
}


def _get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the audit DB, or another file — ``verify`` points this at a copy."""
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
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
                    email_sent          INTEGER NOT NULL DEFAULT 0,
                    input_guard_findings TEXT
                )
            """)
            _apply_migrations(conn)
            ensure_chain(conn)
            conn.commit()
    except Exception as exc:
        logger.warning("audit init_db failed: %s", exc)


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add columns that a table created by an earlier version is missing.

    ``CREATE TABLE IF NOT EXISTS`` does not widen an existing table, so a
    deployment carrying an older ``audit.db`` would fail every insert and the
    audit trail would go quiet — which is the one failure this log cannot have.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
    for column, statement in _MIGRATIONS.items():
        if column not in existing:
            conn.execute(statement)


def _json_list(value: str | None) -> list:
    """Decode a JSON-encoded list column, tolerating a NULL or a bad value."""
    try:
        return json.loads(value or "[]")
    except Exception:
        return []


def _chain_row(conn: sqlite3.Connection, kind: str, run_id: str) -> None:
    """Append a tamper-evidence entry for the row as it now stands.

    The snapshot is the row read straight back out of SQLite rather than the
    ``state`` dict that produced it: what the chain has to vouch for is what the
    file says, and a digest over the intent would miss a write that landed
    differently. Called before the commit, inside the write transaction — see
    ``chain.append_entry`` for why the order matters.

    Because it runs before the commit, a failure here rolls the row back with
    it. That is the intended trade: a row that got written without a chain entry
    would be reported as unchained by every verification from then on, and a
    verifier that reports a permanent false alarm is one nobody reads.
    """
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        # An UPDATE against an unknown run_id changes nothing, so there is no
        # row to vouch for and nothing to record.
        return
    append_entry(conn, kind=kind, run_id=run_id, payload=dict(row))


def verify_audit_chain(db_path: Path | None = None) -> ChainVerification:
    """Walk the audit log's hash chain and report the first entry that breaks.

    Unlike the write paths in this module, this does not swallow errors. A
    writer that gives up quietly loses one row; a verifier that reports "fine"
    because it could not read the file is worse than having no verifier.
    """
    with _get_conn(db_path) as conn:
        return verify_chain(conn)


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
                    root_cause, rca_summary, recommended_fix, email_sent,
                    input_guard_findings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(state.get("input_guard_findings") or []),
                ),
            )
            _chain_row(conn, "run_started", run_id)
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
            _chain_row(conn, "run_completed", run_id)
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
                # Decode JSON-encoded list columns back to Python lists
                r["affected_systems"] = _json_list(r.get("affected_systems"))
                r["input_guard_findings"] = _json_list(r.get("input_guard_findings"))
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
            r["affected_systems"] = _json_list(r.get("affected_systems"))
            r["input_guard_findings"] = _json_list(r.get("input_guard_findings"))
            return r
    except Exception as exc:
        logger.warning("audit get_run failed: %s", exc)
        return None
