"""Tests for the custom MCP server tool registrations.

The server wraps the same underlying tool functions exercised in test_tools.py.
Here we verify the MCP tool functions are registered and callable end-to-end.
"""
from backend.mcp_server import server


class TestMcpToolRegistration:
    def test_server_instance_exists(self) -> None:
        assert server.mcp is not None

    def test_fetch_jira_incident(self) -> None:
        assert server.fetch_jira_incident("INC-101")["id"] == "INC-101"

    def test_comment_on_jira(self) -> None:
        result = server.comment_on_jira("INC-1", "note", "In Progress")
        assert result["comment_added"] == "note"

    def test_search_past_incidents(self) -> None:
        assert isinstance(server.search_past_incidents("auth"), list)

    def test_fetch_logs(self) -> None:
        assert any("503" in line for line in server.fetch_logs("auth-service"))

    def test_fetch_metrics(self) -> None:
        assert server.fetch_metrics("payment-service")["service"] == "payment-service"

    def test_fetch_deployments(self) -> None:
        assert isinstance(server.fetch_deployments("payment-service"), list)

    def test_notify_via_email(self) -> None:
        assert server.notify_via_email(["a@x.com"], "subj", "body", "P1")["sent"] is True
