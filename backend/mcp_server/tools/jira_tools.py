"""Mock Jira tools — swap HTTP calls for real Jira SDK when credentials are ready."""
from datetime import datetime


def get_jira_incident(incident_id: str) -> dict:
    return {
        "id": incident_id,
        "title": "Auth service returning 503 errors",
        "description": (
            "Users are unable to log in. The auth service has been returning "
            "503 Service Unavailable since 14:32 UTC. Affects all regions."
        ),
        "reporter": "jane.doe@company.com",
        "created_at": datetime.utcnow().isoformat(),
        "status": "Open",
        "priority": "High",
    }


def update_jira_ticket(incident_id: str, comment: str, status: str = None) -> dict:
    result = {"incident_id": incident_id, "comment_added": comment}
    if status:
        result["status_changed_to"] = status
    return result


def search_jira_incidents(query: str) -> list[dict]:
    return [
        {
            "id": "INC-088",
            "title": "Auth service 502 errors — DB connection pool exhausted",
            "resolved_at": "2025-03-10T09:15:00",
            "root_cause": "PostgreSQL max_connections limit hit under traffic spike",
            "fix": "Increased connection pool size and added circuit breaker",
        }
    ]
