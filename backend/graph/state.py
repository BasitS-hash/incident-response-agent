from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages


class IncidentState(TypedDict):
    # --- Incident core fields (set at intake) ---
    incident_id: str
    title: str
    description: str
    reporter: str
    created_at: str

    # --- Triage output ---
    severity: Optional[str]          # P1, P2, P3, P4
    affected_systems: list[str]
    triage_notes: Optional[str]
    similar_incidents: list[dict]    # from Mem0

    # --- RCA output ---
    root_cause: Optional[str]
    rca_summary: Optional[str]
    log_evidence: list[str]
    recommended_fix: Optional[str]

    # --- HITL ---
    approved: Optional[bool]
    approver: Optional[str]
    approval_notes: Optional[str]

    # --- Notification ---
    email_sent: bool
    notification_recipients: list[str]

    # --- Agent message history (append-only) ---
    messages: Annotated[list, add_messages]
