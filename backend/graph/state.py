from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


def merge_guard_findings(
    existing: list[str] | str | None,
    update: list[str] | str | None,
) -> list[str]:
    """Accumulate input-guard findings across nodes without repeating them.

    Intake, triage and RCA each re-wrap the ticket text for their own prompt, so
    the same field is reported more than once, and RCA runs a second time when an
    approval is rejected. An approver reading the audit row needs the list of
    distinct things the guard changed, not one line per model call.
    """
    merged: list[str] = []
    for side in (existing, update):
        if not side:
            continue
        items = [side] if isinstance(side, str) else side
        for item in items:
            if item not in merged:
                merged.append(item)
    return merged


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

    # What backend/security/untrusted.py changed on the way in — carried on state
    # so it reaches the audit log and the approver, not just the agent that saw it.
    input_guard_findings: Annotated[list[str], merge_guard_findings]

    messages: Annotated[list, add_messages]
