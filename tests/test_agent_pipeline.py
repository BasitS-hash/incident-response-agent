"""Integration-style tests for the agent run functions with a mocked LLM.

These cover the core incident-response logic end-to-end at the agent level:
intake parsing, triage severity assignment + memory enrichment, RCA evidence
gathering, and notification dispatch — all without real LLM or network calls.
"""
import json

import pytest

from backend.agents import intake_agent, notify_agent, rca_agent, triage_agent

# ── intake_agent.run_intake ─────────────────────────────────────────────────

class TestRunIntake:
    def test_parses_valid_llm_json(self, fake_llm_factory) -> None:
        fake_llm_factory(
            "backend.agents.intake_agent",
            json.dumps({
                "incident_id": "INC-101",
                "title": "Auth down",
                "description": "503s",
                "reporter": "jane@x.com",
                "created_at": "2026-01-01T00:00:00",
            }),
        )
        result = intake_agent.run_intake("INC-101")
        assert result["incident_id"] == "INC-101"
        assert result["title"] == "Auth down"
        assert "messages" in result

    def test_falls_back_to_raw_jira_on_bad_json(self, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.intake_agent", "this is not json")
        result = intake_agent.run_intake("INC-101")
        # Falls back to the raw Jira record for INC-101
        assert result["incident_id"] == "INC-101"
        assert "503" in result["title"]

    def test_strips_markdown_fence(self, fake_llm_factory) -> None:
        fenced = "```json\n" + json.dumps({"incident_id": "INC-205", "title": "Pay"}) + "\n```"
        fake_llm_factory("backend.agents.intake_agent", fenced)
        result = intake_agent.run_intake("INC-205")
        assert result["incident_id"] == "INC-205"
        assert result["title"] == "Pay"


# ── triage_agent.run_triage ─────────────────────────────────────────────────

class TestRunTriage:
    @pytest.fixture(autouse=True)
    def no_memory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(triage_agent, "search_similar_incidents", lambda _d: [])

    def test_assigns_severity_from_llm(self, fake_llm_factory) -> None:
        fake_llm_factory(
            "backend.agents.triage_agent",
            json.dumps({
                "severity": "P1",
                "affected_systems": ["auth-service"],
                "triage_notes": "Total outage",
            }),
        )
        state = {"title": "Auth down", "description": "503 everywhere"}
        result = triage_agent.run_triage(state)
        assert result["severity"] == "P1"
        assert result["affected_systems"] == ["auth-service"]
        assert result["triage_notes"] == "Total outage"

    def test_defaults_severity_p3_when_missing(self, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.triage_agent", "no json here")
        state = {"title": "x", "description": "y"}
        result = triage_agent.run_triage(state)
        assert result["severity"] == "P3"
        assert result["affected_systems"] == []

    def test_injects_similar_incident_memory(self, monkeypatch, fake_llm_factory) -> None:
        captured = {}

        class _LLM:
            def invoke(self, messages):
                captured["prompt"] = messages[1].content
                from tests.conftest import FakeLLMResponse
                return FakeLLMResponse(content=json.dumps({"severity": "P2"}))

        monkeypatch.setattr(triage_agent, "get_cached_llm", lambda: _LLM())
        monkeypatch.setattr(
            triage_agent, "search_similar_incidents",
            lambda _d: [{"memory": "Past Redis OOM resolved by pool bump"}],
        )
        result = triage_agent.run_triage({"title": "t", "description": "Redis issues"})
        assert "Redis OOM" in captured["prompt"]
        assert result["similar_incidents"][0]["memory"].startswith("Past Redis")

    def test_caps_injected_memory_length(self, monkeypatch, fake_llm_factory) -> None:
        captured = {}

        class _LLM:
            def invoke(self, messages):
                captured["prompt"] = messages[1].content
                from tests.conftest import FakeLLMResponse
                return FakeLLMResponse(content=json.dumps({"severity": "P3"}))

        monkeypatch.setattr(triage_agent, "get_cached_llm", lambda: _LLM())
        monkeypatch.setattr(
            triage_agent, "search_similar_incidents",
            lambda _d: [{"memory": "Z" * 2000}],
        )
        triage_agent.run_triage({"title": "t", "description": "d"})
        # The injected snippet is capped at 500 chars
        assert "Z" * 500 in captured["prompt"]
        assert "Z" * 501 not in captured["prompt"]


# ── rca_agent.run_rca ───────────────────────────────────────────────────────

class TestRunRca:
    def test_gathers_evidence_and_parses_fix(self, fake_llm_factory) -> None:
        fake_llm_factory(
            "backend.agents.rca_agent",
            json.dumps({
                "root_cause": "Redis pool too small",
                "rca_summary": "Pool reduction caused cache miss storm",
                "log_evidence": ["err1", "err2"],
                "recommended_fix": "Restore pool size to 100",
            }),
        )
        state = {
            "title": "Auth down",
            "severity": "P1",
            "description": "503s",
            "affected_systems": ["auth-service"],
        }
        result = rca_agent.run_rca(state)
        assert result["root_cause"] == "Redis pool too small"
        assert result["recommended_fix"] == "Restore pool size to 100"
        assert result["log_evidence"] == ["err1", "err2"]

    def test_handles_missing_affected_systems(self, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.rca_agent", json.dumps({"root_cause": "x"}))
        state = {"title": "t", "severity": "P2", "description": "d", "affected_systems": []}
        result = rca_agent.run_rca(state)
        assert result["root_cause"] == "x"

    def test_coerces_nonstring_fields(self, fake_llm_factory) -> None:
        fake_llm_factory(
            "backend.agents.rca_agent",
            json.dumps({
                "root_cause": {"nested": "obj"},
                "recommended_fix": ["step1", "step2"],
            }),
        )
        state = {"title": "t", "severity": "P3", "description": "d", "affected_systems": ["auth"]}
        result = rca_agent.run_rca(state)
        assert isinstance(result["root_cause"], str)
        assert "nested" in result["root_cause"]
        assert result["recommended_fix"] == "step1; step2"

    def test_fallback_when_no_json(self, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.rca_agent", "plain text reply")
        state = {"title": "t", "severity": "P3", "description": "d", "affected_systems": ["auth"]}
        result = rca_agent.run_rca(state)
        assert result["root_cause"] == "Unable to determine"


# ── notify_agent.run_notify ─────────────────────────────────────────────────

class TestRunNotify:
    def test_sends_email_and_stores_memory(self, monkeypatch, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.notify_agent", "Email body content")
        sent = {}
        stored = {}
        monkeypatch.setattr(
            notify_agent, "send_email_notification",
            lambda to, subject, body, severity: sent.update(
                {"to": to, "subject": subject, "severity": severity}
            ),
        )
        monkeypatch.setattr(
            notify_agent, "store_resolved_incident",
            lambda iid, state: stored.update({"id": iid}),
        )
        state = {
            "incident_id": "INC-101",
            "title": "Auth down",
            "severity": "P1",
            "affected_systems": ["auth-service"],
            "root_cause": "pool",
            "rca_summary": "summary",
            "recommended_fix": "fix",
            "approver": "Alice",
            "approval_notes": "ok",
            "notification_recipients": ["ops@x.com"],
        }
        result = notify_agent.run_notify(state)
        assert result["email_sent"] is True
        assert sent["to"] == ["ops@x.com"]
        assert "P1" in sent["subject"]
        assert stored["id"] == "INC-101"

    def test_raises_without_recipients(self, monkeypatch, fake_llm_factory) -> None:
        fake_llm_factory("backend.agents.notify_agent", "body")
        monkeypatch.setattr(notify_agent, "send_email_notification", lambda **k: None)
        monkeypatch.setattr(notify_agent, "store_resolved_incident", lambda *a: None)
        state = {
            "incident_id": "INC-1", "title": "t", "severity": "P2",
            "affected_systems": [], "root_cause": "r", "rca_summary": "s",
            "recommended_fix": "f", "notification_recipients": [],
        }
        with pytest.raises(ValueError, match="recipients"):
            notify_agent.run_notify(state)
