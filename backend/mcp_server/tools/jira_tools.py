from datetime import datetime

_MOCK_INCIDENTS: dict[str, dict] = {
    "INC-101": {
        "title": "Auth service returning 503 errors",
        "description": (
            "Users are unable to log in. The auth service has been returning "
            "503 Service Unavailable since 14:32 UTC. Affects all regions."
        ),
        "reporter": "jane.doe@company.com",
        "priority": "High",
    },
    "INC-205": {
        "title": "Payment service database connection timeout",
        "description": (
            "Checkout is failing for all users. The payment service cannot reach "
            "the PostgreSQL database — connection timeouts spiking to 30s since "
            "09:15 UTC. Orders are not being processed. Revenue impact confirmed."
        ),
        "reporter": "john.smith@company.com",
        "priority": "Critical",
    },
    "INC-312": {
        "title": "Notification service bulk email delivery failure",
        "description": (
            "Transactional emails (password reset, order confirmations, alerts) have "
            "stopped delivering since 11:40 UTC. SES bounce rate exceeded the account "
            "threshold and AWS auto-suspended sending. 14,000+ emails are queued in the "
            "dead-letter queue. Customer support ticket volume up 300%."
        ),
        "reporter": "priya.patel@company.com",
        "priority": "High",
    },
}

_DEFAULT_INCIDENT = {
    "title": "Unknown incident",
    "description": "No details available for this incident ID.",
    "reporter": "system@company.com",
    "priority": "Medium",
}


def get_jira_incident(incident_id: str) -> dict:
    data = _MOCK_INCIDENTS.get(incident_id, {**_DEFAULT_INCIDENT})
    return {
        "id": incident_id,
        "title": data["title"],
        "description": data["description"],
        "reporter": data["reporter"],
        "created_at": datetime.utcnow().isoformat(),
        "status": "Open",
        "priority": data["priority"],
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
