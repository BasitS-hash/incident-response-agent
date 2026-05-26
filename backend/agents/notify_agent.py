"""Notify agent — composes and sends the RCA summary email after human approval."""
from langchain_core.messages import SystemMessage, HumanMessage
from backend.mcp_server.tools.email_tools import send_email_notification
from backend.memory.mem0_client import store_resolved_incident
from backend.agents.llm_factory import get_llm

llm = get_llm()

SYSTEM_PROMPT = """You are an incident communications agent. Write a clear, professional
incident notification email body. Include: what happened, severity, affected systems,
root cause, recommended fix, and next steps. Keep it under 300 words."""

def run_notify(state: dict) -> dict:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Incident: {state['title']}\n"
                f"Severity: {state['severity']}\n"
                f"Affected Systems: {', '.join(state.get('affected_systems', []))}\n"
                f"Root Cause: {state['root_cause']}\n"
                f"RCA Summary: {state['rca_summary']}\n"
                f"Recommended Fix: {state['recommended_fix']}\n"
                f"Approved by: {state.get('approver', 'unknown')}\n"
                f"Approval Notes: {state.get('approval_notes', '')}"
            )
        ),
    ]

    response = llm.invoke(messages)
    email_body = response.content

    subject = f"[{state['severity']}] Incident RCA: {state['title']}"
    recipients = state.get("notification_recipients") or []
    if not recipients:
        raise ValueError(
            "No notification recipients configured. "
            "Pass recipients when starting the incident or set SMTP_TO in .env."
        )

    send_email_notification(
        to=recipients,
        subject=subject,
        body=email_body,
        severity=state["severity"],
    )

    store_resolved_incident(state["incident_id"], state)

    return {
        "email_sent": True,
        "messages": [response],
    }
