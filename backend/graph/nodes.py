"""Graph node wrappers — each function maps IncidentState in → IncidentState update out."""
from backend.graph.state import IncidentState
from backend.agents.intake_agent import run_intake
from backend.agents.triage_agent import run_triage
from backend.agents.rca_agent import run_rca
from backend.agents.notify_agent import run_notify


def intake_node(state: IncidentState) -> dict:
    return run_intake(state["incident_id"])


def triage_node(state: IncidentState) -> dict:
    return run_triage(state)


def rca_node(state: IncidentState) -> dict:
    return run_rca(state)


def approval_node(state: IncidentState) -> dict:
    """
    This node is the HITL interrupt point.
    The graph pauses here automatically (interrupt_before=["approval"]).
    It resumes when the API receives POST /approve/{run_id}.
    """
    return {}


def notify_node(state: IncidentState) -> dict:
    return run_notify(state)


def route_after_triage(state: IncidentState) -> str:
    """P1 incidents skip RCA and go straight to notify for speed."""
    if state.get("severity") == "P1":
        return "approval"
    return "rca"


def route_after_approval(state: IncidentState) -> str:
    """If rejected, loop back to RCA for re-analysis."""
    if state.get("approved") is False:
        return "rca"
    return "notify"
