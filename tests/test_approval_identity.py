"""The approver recorded in the audit log is the one the credential names.

``test_api_endpoints.py`` covers auth as a yes/no gate. These tests cover the
narrower question the audit log actually has to answer: when the chain attests
to an approver, is that name something the caller could have chosen?

The happy path here runs the real graph (ephemeral checkpointer, stubbed agent
functions) against the real audit log on a temp DB, because the thing worth
asserting is what ends up in the row and in the chain — not what the handler
passed to a mock.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

import backend.api.main as api_main
import backend.audit.log as audit_module
from backend.graph import nodes, workflow
from backend.security.principals import SCOPE_APPROVE, SCOPE_SUBMIT, Principal

APPROVER_KEY = "approver-key-aaaaaaaaaaaaaaaa"
SUBMITTER_KEY = "submitter-key-bbbbbbbbbbbbbbbb"

PRINCIPALS = {
    APPROVER_KEY: Principal(
        name="alice@corp.com", scopes=frozenset({SCOPE_SUBMIT, SCOPE_APPROVE})
    ),
    SUBMITTER_KEY: Principal(
        name="pager-bot", scopes=frozenset({SCOPE_SUBMIT})
    ),
}

APPROVER = {"X-API-Key": APPROVER_KEY}
SUBMITTER = {"X-API-Key": SUBMITTER_KEY}


@pytest.fixture
def notify_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Stub the agent functions the graph nodes delegate to, and count notifies.

    ``notify`` firing twice (or zero times) for one approval is the failure the
    identity change could plausibly introduce, so the count is an assertion
    rather than a side note.
    """
    calls: list[dict] = []
    monkeypatch.setattr(nodes, "run_intake", lambda iid: {
        "incident_id": iid, "title": "Auth 503s", "description": "d",
        "reporter": "jane@x.com", "created_at": "2026-01-01T00:00:00",
    })
    monkeypatch.setattr(nodes, "run_triage", lambda s: {
        "severity": "P1", "affected_systems": ["auth-service"],
        "triage_notes": "total outage",
    })
    monkeypatch.setattr(nodes, "run_rca", lambda s: {
        "root_cause": "pool reduced by deploy", "rca_summary": "summary",
        "recommended_fix": "restore pool size",
    })

    def _notify(state: dict) -> dict:
        calls.append(dict(state))
        return {"email_sent": True}

    monkeypatch.setattr(nodes, "run_notify", _notify)
    return calls


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, notify_calls):
    """A TestClient wired to the real graph and the real audit log on a temp DB."""
    monkeypatch.setattr(audit_module, "_DB_PATH", tmp_path / "audit.db")
    audit_module.init_db()

    # The limiter's counters live on the module-level limiter, so without this
    # the per-IP budget is shared across tests and whichever runs last gets 429s.
    api_main.limiter.reset()

    monkeypatch.setattr(api_main, "API_KEY", "")
    monkeypatch.setattr(api_main, "API_PRINCIPALS", PRINCIPALS)
    monkeypatch.setattr(api_main, "graph_app", workflow.build_graph(MemorySaver()))
    monkeypatch.setattr(api_main, "get_callback_handler", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "flush", lambda: None)
    monkeypatch.setattr(api_main, "validate_config", lambda: [])
    monkeypatch.setattr(api_main, "init_db", lambda: None)

    with TestClient(api_main.api) as c:
        yield c


def _start_run(client) -> str:
    resp = client.post("/incident", json={"incident_id": "INC-101"}, headers=APPROVER)
    assert resp.status_code == 200
    return resp.json()["run_id"]


def _row(run_id: str) -> dict:
    run = audit_module.get_run(run_id)
    assert run is not None
    return run


# ── the recorded approver comes from the credential ───────────────────────

class TestRecordedApprover:
    def test_approval_records_the_principal_bound_to_the_key(
        self, client, notify_calls
    ) -> None:
        run_id = _start_run(client)
        resp = client.post(
            f"/approve/{run_id}", json={"approved": True}, headers=APPROVER
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["email_sent"] is True
        assert body["approver"] == "alice@corp.com"

        row = _row(run_id)
        assert row["approver"] == "alice@corp.com"
        assert row["approved"] == 1
        assert len(notify_calls) == 1

    def test_the_body_cannot_choose_a_different_name(self, client) -> None:
        """The whole point: a caller holding a key cannot approve as someone
        else, and the chain is never asked to attest to a name they typed."""
        run_id = _start_run(client)
        resp = client.post(
            f"/approve/{run_id}",
            json={"approved": True, "approver": "the-cto"},
            headers=APPROVER,
        )
        assert resp.status_code == 403
        assert "does not match" in resp.json()["detail"]

        row = _row(run_id)
        assert row["approver"] is None
        assert row["status"] == "awaiting_approval"

    def test_a_body_that_agrees_with_the_credential_is_accepted(self, client) -> None:
        """The frontend no longer sends it, but an older client that does is
        not broken for agreeing."""
        run_id = _start_run(client)
        resp = client.post(
            f"/approve/{run_id}",
            json={"approved": True, "approver": "ALICE@corp.com"},
            headers=APPROVER,
        )
        assert resp.status_code == 200
        assert _row(run_id)["approver"] == "alice@corp.com"

    def test_rejection_records_the_principal_too(self, client, notify_calls) -> None:
        run_id = _start_run(client)
        resp = client.post(
            f"/approve/{run_id}",
            json={"approved": False, "notes": "need more evidence"},
            headers=APPROVER,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert resp.json()["approver"] == "alice@corp.com"
        row = _row(run_id)
        assert row["approver"] == "alice@corp.com"
        assert row["approved"] == 0
        assert notify_calls == []


# ── the chain still verifies over the derived identity ────────────────────

class TestChainAfterBoundApproval:
    def test_chain_verifies_clean_after_an_approval(self, client) -> None:
        run_id = _start_run(client)
        client.post(f"/approve/{run_id}", json={"approved": True}, headers=APPROVER)

        result = audit_module.verify_audit_chain()
        assert result.ok, result.report()
        assert result.rows_checked == 1

    def test_rewriting_the_recorded_approver_is_still_caught(self, client) -> None:
        """The chain's job after this change is unchanged — but now the field it
        is protecting is one the caller never got to set."""
        import sqlite3

        run_id = _start_run(client)
        client.post(f"/approve/{run_id}", json={"approved": True}, headers=APPROVER)

        conn = sqlite3.connect(str(audit_module._DB_PATH))
        try:
            conn.execute(
                "UPDATE runs SET approver = ? WHERE run_id = ?", ("the-cto", run_id)
            )
            conn.commit()
        finally:
            conn.close()

        result = audit_module.verify_audit_chain()
        assert not result.ok
        problem = result.first_problem
        assert problem is not None
        assert problem.kind == "row_altered"
        assert "approver" in problem.detail


# ── scopes: filing an incident is not authorising a page ──────────────────

class TestScopeSplit:
    def test_a_submit_only_key_cannot_approve(self, client, notify_calls) -> None:
        run_id = _start_run(client)
        resp = client.post(
            f"/approve/{run_id}", json={"approved": True}, headers=SUBMITTER
        )
        assert resp.status_code == 403
        assert notify_calls == []
        assert _row(run_id)["status"] == "awaiting_approval"

    def test_a_submit_only_key_can_still_file_an_incident(self, client) -> None:
        resp = client.post(
            "/incident", json={"incident_id": "INC-202"}, headers=SUBMITTER
        )
        assert resp.status_code == 200

    def test_a_refused_approval_leaves_the_run_resumable(
        self, client, notify_calls
    ) -> None:
        """Fail closed, not fail broken: the gate is still open for a key that
        does hold the scope."""
        run_id = _start_run(client)
        client.post(f"/approve/{run_id}", json={"approved": True}, headers=SUBMITTER)
        resp = client.post(
            f"/approve/{run_id}", json={"approved": True}, headers=APPROVER
        )
        assert resp.status_code == 200
        assert _row(run_id)["approver"] == "alice@corp.com"
        assert len(notify_calls) == 1
