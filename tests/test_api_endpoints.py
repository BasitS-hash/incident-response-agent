"""HTTP-level tests for the FastAPI endpoints with the graph and stores mocked.

These exercise auth enforcement, validation wiring, and the safe-state response
shape without invoking any real LLM or LangGraph execution.
"""
import pytest
from fastapi.testclient import TestClient

import backend.api.main as api_main


@pytest.fixture
def client(monkeypatch):
    """A TestClient with API key auth enabled and the graph/audit store stubbed."""
    monkeypatch.setattr(api_main, "API_KEY", "test-key")

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
            json={"approved": True, "approver": "Alice"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_reject_returns_rejected(self, client) -> None:
        resp = client.post(
            "/approve/some-run-id",
            json={"approved": False, "approver": "Bob"},
            headers=HEADERS,
        )
        assert resp.json()["status"] == "rejected"

    def test_invalid_approver_rejected(self, client) -> None:
        resp = client.post(
            "/approve/run-id",
            json={"approved": True, "approver": "<script>alert(1)</script>"},
            headers=HEADERS,
        )
        assert resp.status_code == 422


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
