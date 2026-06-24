"""Tests for backend/audit/log.py — SQLite run history store."""
import uuid
from pathlib import Path

import pytest

# ── Override the DB path to a temp file so tests never touch the real DB ──
import backend.audit.log as audit_module


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the audit DB to a fresh temp file for every test."""
    monkeypatch.setattr(audit_module, "_DB_PATH", tmp_path / "test_audit.db")
    audit_module.init_db()


def _run_id() -> str:
    return str(uuid.uuid4())


# ── init_db ───────────────────────────────────────────────────────────────

def test_init_db_creates_table(tmp_path: Path) -> None:
    """init_db is idempotent — calling it twice raises no error."""
    audit_module.init_db()  # second call
    runs = audit_module.get_all_runs()
    assert isinstance(runs, list)


# ── record_run_started ────────────────────────────────────────────────────

def test_record_run_started_inserts_row() -> None:
    rid = _run_id()
    state = {
        "severity": "P2",
        "affected_systems": ["auth-service", "redis"],
        "triage_notes": "Redis OOM",
        "root_cause": "Memory leak",
        "rca_summary": "Unclosed connections",
        "recommended_fix": "Upgrade redis-py",
        "email_sent": False,
    }
    audit_module.record_run_started(rid, "INC-101", state)

    runs = audit_module.get_all_runs()
    assert len(runs) == 1
    r = runs[0]
    assert r["run_id"] == rid
    assert r["incident_id"] == "INC-101"
    assert r["status"] == "awaiting_approval"
    assert r["severity"] == "P2"
    assert r["affected_systems"] == ["auth-service", "redis"]
    assert r["email_sent"] == 0


def test_record_run_started_handles_empty_state() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-999", {})
    runs = audit_module.get_all_runs()
    assert len(runs) == 1
    assert runs[0]["severity"] is None
    assert runs[0]["affected_systems"] == []


def test_record_run_started_email_sent_flag() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-200", {"email_sent": True})
    r = audit_module.get_run(rid)
    assert r is not None
    assert r["email_sent"] == 1


# ── record_run_completed ──────────────────────────────────────────────────

def test_record_run_completed_approved() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-101", {"severity": "P1"})
    audit_module.record_run_completed(rid, {
        "approved": True,
        "approver": "Alice Chen",
        "approval_notes": "LGTM",
        "email_sent": True,
        "severity": "P1",
        "root_cause": "DB timeout",
        "rca_summary": "Query plan regression",
        "recommended_fix": "Add index",
    })

    r = audit_module.get_run(rid)
    assert r is not None
    assert r["status"] == "completed"
    assert r["approved"] == 1
    assert r["approver"] == "Alice Chen"
    assert r["email_sent"] == 1
    assert r["completed_at"] is not None


def test_record_run_completed_rejected() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-102", {})
    audit_module.record_run_completed(rid, {
        "approved": False,
        "approver": "Bob",
        "approval_notes": "Need more info",
        "email_sent": False,
    })

    r = audit_module.get_run(rid)
    assert r is not None
    assert r["status"] == "rejected"
    assert r["approved"] == 0


def test_record_run_completed_preserves_existing_fields() -> None:
    """COALESCE logic: fields already set at started time are not cleared."""
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-103", {"severity": "P3", "root_cause": "Disk full"})
    # completed state omits severity/root_cause — should keep the started values
    audit_module.record_run_completed(rid, {
        "approved": True,
        "approver": "Carol",
        "email_sent": False,
    })

    r = audit_module.get_run(rid)
    assert r is not None
    assert r["severity"] == "P3"
    assert r["root_cause"] == "Disk full"


# ── get_all_runs ──────────────────────────────────────────────────────────

def test_get_all_runs_returns_newest_first() -> None:
    for i in range(3):
        rid = _run_id()
        audit_module.record_run_started(rid, f"INC-{100 + i}", {})

    runs = audit_module.get_all_runs()
    assert len(runs) == 3
    # started_at should be descending (newest first)
    dates = [r["started_at"] for r in runs]
    assert dates == sorted(dates, reverse=True)


def test_get_all_runs_limit() -> None:
    for i in range(5):
        audit_module.record_run_started(_run_id(), f"INC-{i}", {})

    runs = audit_module.get_all_runs(limit=3)
    assert len(runs) == 3


def test_get_all_runs_decodes_affected_systems() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-200", {
        "affected_systems": ["api", "db", "cache"],
    })
    runs = audit_module.get_all_runs()
    assert runs[0]["affected_systems"] == ["api", "db", "cache"]


# ── get_run ───────────────────────────────────────────────────────────────

def test_get_run_returns_none_for_missing() -> None:
    result = audit_module.get_run("does-not-exist")
    assert result is None


def test_get_run_returns_correct_record() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-777", {"severity": "P4"})
    r = audit_module.get_run(rid)
    assert r is not None
    assert r["run_id"] == rid
    assert r["severity"] == "P4"


def test_get_run_decodes_affected_systems() -> None:
    rid = _run_id()
    audit_module.record_run_started(rid, "INC-888", {
        "affected_systems": ["payment-svc"],
    })
    r = audit_module.get_run(rid)
    assert r is not None
    assert r["affected_systems"] == ["payment-svc"]
