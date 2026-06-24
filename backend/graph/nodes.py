from backend.agents.intake_agent import run_intake
from backend.agents.notify_agent import run_notify
from backend.agents.rca_agent import run_rca
from backend.agents.triage_agent import run_triage
from backend.graph.state import IncidentState


def intake_node(state: IncidentState) -> dict:
    return run_intake(state["incident_id"])


def triage_node(state: IncidentState) -> dict:
    return run_triage(state)


def rca_node(state: IncidentState) -> dict:
    return run_rca(state)


def approval_node(state: IncidentState) -> dict:
    return {}


def notify_node(state: IncidentState) -> dict:
    return run_notify(state)


def route_after_triage(state: IncidentState) -> str:
    return "rca"


def route_after_approval(state: IncidentState) -> str:
    if state.get("approved") is False:
        return "rca"
    return "notify"
