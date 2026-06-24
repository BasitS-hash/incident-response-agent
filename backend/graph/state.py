from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class IncidentState(TypedDict):
    incident_id: str
    title: str
    description: str
    reporter: str
    created_at: str

    severity: str | None
    affected_systems: list[str]
    triage_notes: str | None
    similar_incidents: list[dict]

    root_cause: str | None
    rca_summary: str | None
    log_evidence: list[str]
    recommended_fix: str | None

    approved: bool | None
    approver: str | None
    approval_notes: str | None

    email_sent: bool
    notification_recipients: list[str]

    messages: Annotated[list, add_messages]
