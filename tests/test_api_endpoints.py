"""HTTP-level tests for the FastAPI endpoints with the graph and stores mocked.

These exercise auth enforcement, validation wiring, and the safe-state response
shape without invoking any real LLM or LangGraph execution. What the audit log
ends up recording for an approval is covered in ``test_approval_identity.py``.
"""
import pytest
from fastapi.testclient import TestClient

import backend.api.main as api_main
from backend.security.principals import SCOPE_APPROVE, SCOPE_SUBMIT, Principal

# A named key that may approve, alongside the legacy shared ``API_KEY`` below.
APPROVER_KEY = "approver-key-aaaaaaaaaaaaaaaa"
SUBMITTER_KEY = "submitter-key-bbbbbbbbbbbbbbbb"
PRINCIPALS = {
    APPROVER_KEY: Principal(
        name="alice@corp.com", scopes=frozenset({SCOPE_SUBMIT, SCOPE_APPROVE})
    ),
    SUBMITTER_KEY: Principal(name="pager-bot", scopes=frozenset({SCOPE_SUBMIT})),
}


@pytest.fixture
def client(monkeypatch):
    """A TestClient with API key auth enabled and the graph/audit store stubbed."""
    monkeypatch.setattr(api_main, "API_KEY", "test-key")
    monkeypatch.setattr(api_main, "API_PRINCIPALS", PRINCIPALS)

    class _State:
        def __init__(self, values, next_=()):
            self.values = values
            self.next = next_

    fake_state = _State(
        values={
            "incident_id": "INC-101",
            "severity": "P1",
            "root_cause": "Redis pool too small",
            "rca_summary": "summary",
            "recommended_fix": "Restore pool size",
            "messages": ["should-not-leak"],
            "notification_recipients": ["secret@x.com"],
        },
        next_=("approval",),
    )

    class _Graph:
        def invoke(self, *a, **k):
            return None

        def get_state(self, *a, **k):
            return fake_state

    monkeypatch.setattr(api_main, "graph_app", _Graph())
    monkeypatch.setattr(api_main, "record_run_started", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "record_run_completed", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "get_callback_handler", lambda *a, **k: None)
    monkeypatch.setattr(api_main, "flush", lambda: None)
    # lifespan calls validate_config + init_db; stub both so no creds needed
    monkeypatch.setattr(api_main, "validate_config", lambda: [])
    monkeypatch.setattr(api_main, "init_db", lambda: None)

    with TestClient(api_main.api) as c:
        yield c


HEADERS = {"X-API-Key": "test-key"}
APPROVER_HEADERS = {"X-API-Key": APPROVER_KEY}


class TestHealth:
    def test_health_no_auth_required(self, client) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_incident_rejected_without_key(self, client) -> None:
        resp = client.post("/incident", json={"incident_id": "INC-101"})
        assert resp.status_code == 403

    def test_incident_rejected_with_wrong_key(self, client) -> None:
        resp = client.post(
            "/incident", json={"incident_id": "INC-101"},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 403

    def test_runs_rejected_without_key(self, client) -> None:
        assert client.get("/runs").status_code == 403


class TestStartIncident:
    def test_valid_incident_returns_safe_state(self, client) -> None:
        resp = client.post("/incident", json={"incident_id": "INC-101"}, headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "awaiting_approval"
        assert "run_id" in body
        # Internal keys must be stripped from the response
        assert "messages" not in body["state"]
        assert "notification_recipients" not in body["state"]
        assert body["state"]["severity"] == "P1"

    def test_invalid_incident_id_rejected(self, client) -> None:
        resp = client.post("/incident", json={"incident_id": "not-valid"}, headers=HEADERS)
        assert resp.status_code == 422

    def test_invalid_recipient_email_rejected(self, client) -> None:
        resp = client.post(
            "/incident",
            json={"incident_id": "INC-101", "recipients": ["bad-email"]},
            headers=HEADERS,
        )
        assert resp.status_code == 422


class TestApprove:
    def test_approve_returns_completed(self, client) -> None:
        resp = client.post(
            "/approve/some-run-id",
            json={"approved": True},
            headers=APPROVER_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["approver"] == "alice@corp.com"

    def test_reject_returns_rejected(self, client) -> None:
        resp = client.post(
            "/approve/some-run-id",
            json={"approved": False},
            headers=APPROVER_HEADERS,
        )
        assert resp.json()["status"] == "rejected"

    def test_invalid_approver_rejected(self, client) -> None:
        resp = client.post(
            "/approve/run-id",
            json={"approved": True, "approver": "<script>alert(1)</script>"},
            headers=APPROVER_HEADERS,
        )
        assert resp.status_code == 422


class TestApprovalAuthorisation:
    """Who is allowed to approve, and as whom.

    The hash chain attests to whatever the approver column says, so the only
    thing that makes that column worth attesting to is that the caller could
    not pick it. These are the refusals that hold that line.
    """

    def test_unknown_key_cannot_approve(self, client) -> None:
        resp = client.post(
            "/approve/run-id",
            json={"approved": True},
            headers={"X-API-Key": "not-a-configured-key"},
        )
        assert resp.status_code == 403

    def test_missing_key_cannot_approve(self, client) -> None:
        resp = client.post("/approve/run-id", json={"approved": True})
        assert resp.status_code == 403

    def test_the_legacy_shared_key_cannot_approve(self, client) -> None:
        """``API_KEY`` authenticates but names nobody. An approval recorded
        under it would put a run through the gate with no identity attached,
        so it is refused rather than logged as anonymous."""
        resp = client.post(
            "/approve/run-id", json={"approved": True}, headers=HEADERS
        )
        assert resp.status_code == 403
        assert "API_KEYS" in resp.json()["detail"]

    def test_the_legacy_shared_key_can_still_file_an_incident(self, client) -> None:
        resp = client.post(
            "/incident", json={"incident_id": "INC-101"}, headers=HEADERS
        )
        assert resp.status_code == 200

    def test_a_submit_only_named_key_cannot_approve(self, client) -> None:
        resp = client.post(
            "/approve/run-id",
            json={"approved": True},
            headers={"X-API-Key": SUBMITTER_KEY},
        )
        assert resp.status_code == 403

    def test_an_approve_scoped_key_may_read_the_audit_log(self, client, monkeypatch) -> None:
        """Read endpoints take any valid key — the scope split is about who may
        act, not about who may look."""
        monkeypatch.setattr(api_main, "get_all_runs", lambda limit: [])
        assert client.get("/runs", headers=APPROVER_HEADERS).status_code == 200

    def test_the_response_names_only_the_calling_principal(self, client) -> None:
        resp = client.post(
            "/approve/some-run-id", json={"approved": True}, headers=APPROVER_HEADERS
        )
        body = resp.text
        assert "alice@corp.com" in body
        assert "pager-bot" not in body
        assert APPROVER_KEY not in body


class TestDevMode:
    """With neither ``API_KEY`` nor ``API_KEYS`` set, auth is off by design and
    the startup warning says so. The approver recorded in that mode says so
    too, instead of borrowing a name the caller typed."""

    @pytest.fixture
    def open_client(self, client, monkeypatch):
        monkeypatch.setattr(api_main, "API_KEY", "")
        monkeypatch.setattr(api_main, "API_PRINCIPALS", {})
        return client

    def test_approval_is_recorded_as_unauthenticated(self, open_client) -> None:
        resp = open_client.post("/approve/run-id", json={"approved": True})
        assert resp.status_code == 200
        assert resp.json()["approver"] == "dev-mode-unauthenticated"

    def test_the_body_still_cannot_choose_the_name(self, open_client) -> None:
        resp = open_client.post(
            "/approve/run-id", json={"approved": True, "approver": "the-cto"}
        )
        assert resp.status_code == 403


class TestSearch:
    def test_search_requires_query(self, client, monkeypatch) -> None:
        monkeypatch.setattr(api_main, "search_similar_incidents", lambda q: [])
        resp = client.get("/incidents/search", headers=HEADERS)
        assert resp.status_code == 422  # q is required

    def test_search_returns_results(self, client, monkeypatch) -> None:
        monkeypatch.setattr(api_main, "search_similar_incidents", lambda q: [{"memory": "x"}])
        resp = client.get("/incidents/search?q=redis", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["results"] == [{"memory": "x"}]

    def test_search_rejects_overlong_query(self, client) -> None:
        resp = client.get("/incidents/search?q=" + "a" * 501, headers=HEADERS)
        assert resp.status_code == 422


class TestRuns:
    def test_list_runs(self, client, monkeypatch) -> None:
        monkeypatch.setattr(api_main, "get_all_runs", lambda limit: [{"run_id": "r1"}])
        resp = client.get("/runs", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_run_404(self, client, monkeypatch) -> None:
        monkeypatch.setattr(api_main, "get_run", lambda rid: None)
        resp = client.get("/runs/missing", headers=HEADERS)
        assert resp.status_code == 404

    def test_get_run_found(self, client, monkeypatch) -> None:
        monkeypatch.setattr(api_main, "get_run", lambda rid: {"run_id": rid})
        resp = client.get("/runs/r1", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "r1"


class TestAuditVerify:
    """The endpoint is a convenience for the dashboard — the trustworthy check
    is the CLI run against a copy of the file (see backend/audit/verify.py)."""

    def test_verify_requires_key(self, client) -> None:
        assert client.get("/audit/verify").status_code == 403

    def test_verify_reports_a_clean_chain(self, client, monkeypatch) -> None:
        from backend.audit.chain import ChainVerification

        monkeypatch.setattr(
            api_main, "verify_audit_chain",
            lambda: ChainVerification(entries_checked=5, rows_checked=2),
        )
        resp = client.get("/audit/verify", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["entries_checked"] == 5
        assert body["problems"] == []

    def test_verify_reports_the_first_broken_entry(self, client, monkeypatch) -> None:
        from backend.audit.chain import ChainProblem, ChainVerification

        problem = ChainProblem(
            kind="digest_mismatch", seq=3, run_id="r1", detail="recomputed digest differs",
        )
        monkeypatch.setattr(
            api_main, "verify_audit_chain",
            lambda: ChainVerification(
                entries_checked=3, rows_checked=0, problems=(problem,),
            ),
        )
        resp = client.get("/audit/verify", headers=HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["problems"][0]["seq"] == 3
        assert body["problems"][0]["kind"] == "digest_mismatch"
