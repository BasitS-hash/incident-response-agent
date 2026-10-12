"""Tests for checkpoint durability across a process restart.

The human-in-the-loop gate is only trustworthy if a run parked at the
``approval`` interrupt outlives the process that started it. A restart is
simulated here by discarding the compiled graph *and* the checkpointer and
rebuilding both from the same on-disk DB — nothing is carried over in memory.
"""
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from backend.graph import nodes, workflow

# ── deterministic agents (no LLM, no Jira, no SMTP) ─────────────────────────

NOTIFY_CALLS: list[dict] = []


@pytest.fixture(autouse=True)
def stub_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    NOTIFY_CALLS.clear()
    monkeypatch.setattr(nodes, "run_intake", lambda iid: {
        "incident_id": iid,
        "title": "Redis connection pool exhausted",
        "reporter": "oncall@example.com",
    })
    monkeypatch.setattr(nodes, "run_triage", lambda s: {
        "severity": "P1",
        "affected_systems": ["auth-service", "redis"],
    })
    monkeypatch.setattr(nodes, "run_rca", lambda s: {
        "root_cause": "Deploy #4821 cut the Redis pool from 50 to 5",
        "rca_summary": "97% cache miss rate drove auth-service into OOMKill.",
    })

    def _notify(state: dict) -> dict:
        NOTIFY_CALLS.append(dict(state))
        return {"email_sent": True}

    monkeypatch.setattr(nodes, "run_notify", _notify)


def _initial_state(incident_id: str = "INC-101") -> dict:
    return {"incident_id": incident_id, "messages": []}


# ── the behaviour the README promises ───────────────────────────────────────

def test_pending_approval_survives_process_restart(tmp_path: Path) -> None:
    """A run waiting on a human is resumable after the API process dies."""
    db = tmp_path / "checkpoints.db"
    cfg = {"configurable": {"thread_id": "run-restart"}}

    # ── process 1: run up to the approval gate, then "crash" ──
    first = workflow.build_graph(workflow.get_checkpointer(db))
    first.invoke(_initial_state(), config=cfg)
    assert first.get_state(cfg).next == ("approval",)
    del first

    # ── process 2: nothing in memory, only the file on disk ──
    second = workflow.build_graph(workflow.get_checkpointer(db))
    resumed = second.get_state(cfg)
    assert resumed.next == ("approval",), "pending approval was lost on restart"
    assert resumed.values["incident_id"] == "INC-101"
    assert resumed.values["severity"] == "P1"
    assert resumed.values["root_cause"].startswith("Deploy #4821")

    # ── the human approves in the new process (same call POST /approve makes) ──
    workflow.resume_after_approval(
        second, cfg,
        {"approved": True, "approver": "basit", "approval_notes": "ship the fix"},
    )

    final = second.get_state(cfg)
    assert final.next == ()
    assert final.values["email_sent"] is True
    assert final.values["approver"] == "basit"
    # original pre-restart work is still intact, not re-derived
    assert final.values["incident_id"] == "INC-101"
    assert final.values["severity"] == "P1"
    assert final.values["rca_summary"].startswith("97% cache miss")
    assert len(NOTIFY_CALLS) == 1, "notify must fire exactly once"


def test_memory_saver_drops_pending_approval_on_restart(tmp_path: Path) -> None:
    """Why the on-disk checkpointer is required, pinned as a regression guard.

    An in-memory checkpointer is rebuilt empty by a new process, so the run is
    unreachable — the approval gate silently loses the incident.
    """
    cfg = {"configurable": {"thread_id": "run-ephemeral"}}

    first = workflow.build_graph(MemorySaver())
    first.invoke(_initial_state(), config=cfg)
    assert first.get_state(cfg).next == ("approval",)

    second = workflow.build_graph(MemorySaver())
    assert second.get_state(cfg).values == {}


# ── wiring: where the checkpoint DB lives ───────────────────────────────────

def test_get_checkpointer_defaults_to_the_data_dir() -> None:
    """Checkpoints sit next to the audit DB so one volume holds both."""
    assert workflow._DB_PATH.name == "checkpoints.db"
    assert workflow._DB_PATH.parent.name == "data"
    assert workflow._DB_PATH.parent == (Path(workflow.__file__).parent.parent / "data")


def test_get_checkpointer_creates_the_db_file(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "checkpoints.db"
    app = workflow.build_graph(workflow.get_checkpointer(db))
    app.invoke(_initial_state("INC-205"), config={"configurable": {"thread_id": "t1"}})
    assert db.exists()


# ── the approval gate itself ────────────────────────────────────────────────

def test_resume_does_not_restart_the_run(tmp_path: Path) -> None:
    """Resuming must continue past the gate, not re-run intake/triage/rca.

    Feeding the decision in as graph *input* starts a fresh run that parks at
    the gate again — the approval is accepted by the API and the notification
    is never sent.
    """
    db = tmp_path / "checkpoints.db"
    cfg = {"configurable": {"thread_id": "run-resume"}}
    triage_calls: list[dict] = []

    app = workflow.build_graph(workflow.get_checkpointer(db))
    app.invoke(_initial_state(), config=cfg)

    original_triage = nodes.run_triage
    nodes.run_triage = lambda s: triage_calls.append(dict(s)) or original_triage(s)
    try:
        workflow.resume_after_approval(
            app, cfg, {"approved": True, "approver": "basit", "approval_notes": ""}
        )
    finally:
        nodes.run_triage = original_triage

    assert triage_calls == [], "resume re-ran triage instead of continuing"
    assert app.get_state(cfg).next == ()
    assert len(NOTIFY_CALLS) == 1


def test_second_resume_does_not_notify_twice(tmp_path: Path) -> None:
    """Two approve clicks on the same run must send one notification."""
    db = tmp_path / "checkpoints.db"
    cfg = {"configurable": {"thread_id": "run-double"}}
    decision = {"approved": True, "approver": "basit", "approval_notes": ""}

    app = workflow.build_graph(workflow.get_checkpointer(db))
    app.invoke(_initial_state(), config=cfg)

    workflow.resume_after_approval(app, cfg, decision)
    with pytest.raises(ValueError, match="not awaiting approval"):
        workflow.resume_after_approval(app, cfg, decision)

    assert len(NOTIFY_CALLS) == 1
    assert app.get_state(cfg).next == ()


def test_rejection_does_not_notify(tmp_path: Path) -> None:
    """A rejected run loops back to RCA and parks at the gate — no email."""
    db = tmp_path / "checkpoints.db"
    cfg = {"configurable": {"thread_id": "run-reject"}}

    app = workflow.build_graph(workflow.get_checkpointer(db))
    app.invoke(_initial_state(), config=cfg)
    workflow.resume_after_approval(
        app, cfg, {"approved": False, "approver": "basit", "approval_notes": "need more"}
    )

    assert NOTIFY_CALLS == []
    assert app.get_state(cfg).next == ("approval",)
    assert app.get_state(cfg).values.get("email_sent") is not True


def test_resume_of_unknown_thread_does_not_notify(tmp_path: Path) -> None:
    """A forged run_id has no checkpoint at the gate, so nothing is sent."""
    db = tmp_path / "checkpoints.db"
    app = workflow.build_graph(workflow.get_checkpointer(db))

    with pytest.raises(ValueError, match="not awaiting approval"):
        workflow.resume_after_approval(
            app,
            {"configurable": {"thread_id": "no-such-run"}},
            {"approved": True, "approver": "attacker", "approval_notes": ""},
        )

    assert NOTIFY_CALLS == []
