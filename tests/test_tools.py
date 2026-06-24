"""Tests for the enrichment tools (logs, metrics, deployments, Jira, email).

These are the deterministic data-source adapters the RCA and intake agents call.
"""
import pytest

from backend.mcp_server.tools import email_tools, jira_tools, log_tools

# ── log_tools._service_key (service classification) ────────────────────────

class TestServiceKey:
    @pytest.mark.parametrize(
        "service,expected",
        [
            ("auth-service", "auth"),
            ("AUTH", "auth"),
            ("payment-service", "payment"),
            ("checkout-api", "payment"),
            ("notification-service", "notification"),
            ("email-gateway", "notification"),
            ("ses-worker", "notification"),
            ("unknown-thing", ""),
        ],
    )
    def test_classifies_service(self, service: str, expected: str) -> None:
        assert log_tools._service_key(service) == expected


# ── query_system_logs ──────────────────────────────────────────────────────

class TestQuerySystemLogs:
    def test_known_service_returns_curated_logs(self) -> None:
        logs = log_tools.query_system_logs("auth-service")
        assert any("503" in line for line in logs)
        assert all(isinstance(line, str) for line in logs)

    def test_payment_logs_mention_db(self) -> None:
        logs = log_tools.query_system_logs("payment-service")
        assert any("connection" in line.lower() for line in logs)

    def test_unknown_service_uses_default_template(self) -> None:
        logs = log_tools.query_system_logs("mystery-service")
        assert any("mystery-service" in line for line in logs)
        assert len(logs) == len(log_tools._DEFAULT_LOGS)


# ── get_system_metrics ──────────────────────────────────────────────────────

class TestGetSystemMetrics:
    def test_known_service_metrics_include_service_name(self) -> None:
        metrics = log_tools.get_system_metrics("auth-service")
        assert metrics["service"] == "auth-service"
        assert "error_rate_percent" in metrics

    def test_unknown_service_uses_default_metrics(self) -> None:
        metrics = log_tools.get_system_metrics("xyz")
        assert metrics["service"] == "xyz"
        assert metrics["cpu_percent"] == log_tools._DEFAULT_METRICS["cpu_percent"]

    def test_does_not_mutate_shared_default(self) -> None:
        """Metrics dicts must be copies — mutating one must not leak to the next."""
        a = log_tools.get_system_metrics("xyz")
        a["cpu_percent"] = -999
        b = log_tools.get_system_metrics("abc")
        assert b["cpu_percent"] != -999


# ── get_deployment_history ──────────────────────────────────────────────────

class TestGetDeploymentHistory:
    def test_payment_history_has_orm_migration(self) -> None:
        history = log_tools.get_deployment_history("payment-service")
        assert any("ORM" in d["change"] or "Tortoise" in d["change"] for d in history)

    def test_unknown_service_returns_default(self) -> None:
        history = log_tools.get_deployment_history("xyz")
        assert history == log_tools._DEFAULT_DEPLOYMENTS


# ── jira_tools ──────────────────────────────────────────────────────────────

class TestJiraTools:
    def test_known_incident_returns_full_record(self) -> None:
        inc = jira_tools.get_jira_incident("INC-101")
        assert inc["id"] == "INC-101"
        assert "503" in inc["title"]
        assert inc["status"] == "Open"
        assert "created_at" in inc

    def test_unknown_incident_returns_default(self) -> None:
        inc = jira_tools.get_jira_incident("INC-DOES-NOT-EXIST")
        assert inc["id"] == "INC-DOES-NOT-EXIST"
        assert inc["title"] == jira_tools._DEFAULT_INCIDENT["title"]

    def test_default_does_not_mutate_template(self) -> None:
        inc = jira_tools.get_jira_incident("INC-XXX")
        inc["title"] = "mutated"
        assert jira_tools._DEFAULT_INCIDENT["title"] != "mutated"

    def test_update_ticket_with_status(self) -> None:
        result = jira_tools.update_jira_ticket("INC-1", "looking into it", status="In Progress")
        assert result["comment_added"] == "looking into it"
        assert result["status_changed_to"] == "In Progress"

    def test_update_ticket_without_status(self) -> None:
        result = jira_tools.update_jira_ticket("INC-1", "note only")
        assert "status_changed_to" not in result

    def test_search_returns_list(self) -> None:
        results = jira_tools.search_jira_incidents("auth 503")
        assert isinstance(results, list)
        assert results[0]["id"] == "INC-088"


# ── email_tools (mock sender) ───────────────────────────────────────────────

class TestEmailTools:
    def test_send_returns_sent_envelope(self) -> None:
        result = email_tools.send_email_notification(
            to=["a@example.com", "b@example.com"],
            subject="[P1] Outage",
            body="body text",
            severity="P1",
        )
        assert result["sent"] is True
        assert result["recipients"] == ["a@example.com", "b@example.com"]
        assert result["subject"] == "[P1] Outage"
