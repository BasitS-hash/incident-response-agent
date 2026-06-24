"""WAT — Workflow Agent Tools: custom MCP server exposing all agent tools."""
from mcp.server.fastmcp import FastMCP

from backend.mcp_server.tools.email_tools import send_email_notification
from backend.mcp_server.tools.jira_tools import (
    get_jira_incident,
    search_jira_incidents,
    update_jira_ticket,
)
from backend.mcp_server.tools.log_tools import (
    get_deployment_history,
    get_system_metrics,
    query_system_logs,
)

mcp = FastMCP("WAT - Workflow Agent Tools")


@mcp.tool()
def fetch_jira_incident(incident_id: str) -> dict:
    """Fetch full incident details from Jira by incident ID."""
    return get_jira_incident(incident_id)


@mcp.tool()
def comment_on_jira(incident_id: str, comment: str, status: str = None) -> dict:
    """Add a comment to a Jira ticket and optionally change its status."""
    return update_jira_ticket(incident_id, comment, status)


@mcp.tool()
def search_past_incidents(query: str) -> list[dict]:
    """Search Jira for past incidents similar to the given query."""
    return search_jira_incidents(query)


@mcp.tool()
def fetch_logs(service: str, minutes: int = 30) -> list[str]:
    """Retrieve recent error and warning logs for a given service."""
    return query_system_logs(service, minutes)


@mcp.tool()
def fetch_metrics(service: str) -> dict:
    """Get current system metrics (CPU, memory, connections, error rate) for a service."""
    return get_system_metrics(service)


@mcp.tool()
def fetch_deployments(service: str) -> list[dict]:
    """Get recent deployment history for a service."""
    return get_deployment_history(service)


@mcp.tool()
def notify_via_email(
    to: list[str],
    subject: str,
    body: str,
    severity: str,
) -> dict:
    """Send an email notification with incident RCA summary and severity."""
    return send_email_notification(to, subject, body, severity)


if __name__ == "__main__":
    mcp.run()
