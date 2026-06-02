from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages


class IncidentState(TypedDict):
    incident_id: str
    title: str
    description: str
    reporter: str
    created_at: str

    severity: Optional[str]
    affected_systems: list[str]
    triage_notes: Optional[str]
    similar_incidents: list[dict]

    root_cause: Optional[str]
    rca_summary: Optional[str]
    log_evidence: list[str]
    recommended_fix: Optional[str]

    approved: Optional[bool]
    approver: Optional[str]
    approval_notes: Optional[str]

    email_sent: bool
    notification_recipients: list[str]

    messages: Annotated[list, add_messages]
