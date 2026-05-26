"""LangGraph workflow — wires all nodes and edges into the incident response pipeline."""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from backend.graph.state import IncidentState
from backend.graph.nodes import (
    intake_node,
    triage_node,
    rca_node,
    approval_node,
    notify_node,
    route_after_triage,
    route_after_approval,
)

checkpointer = MemorySaver()


def build_graph():
    graph = StateGraph(IncidentState)

    graph.add_node("intake",   intake_node)
    graph.add_node("triage",   triage_node)
    graph.add_node("rca",      rca_node)
    graph.add_node("approval", approval_node)
    graph.add_node("notify",   notify_node)

    graph.set_entry_point("intake")

    graph.add_edge("intake", "triage")

    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {"rca": "rca", "approval": "approval"},
    )

    graph.add_edge("rca", "approval")

    graph.add_conditional_edges(
        "approval",
        route_after_approval,
        {"rca": "rca", "notify": "notify"},
    )

    graph.add_edge("notify", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["approval"],
    )


app = build_graph()
