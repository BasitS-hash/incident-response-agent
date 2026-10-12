"""LangGraph workflow definition for the incident response playbook.

The graph interrupts before ``approval``, which leaves every run that reaches
the gate suspended in the checkpointer until a human resolves it. That only
holds across a restart if the checkpoints are on disk: an in-memory saver is
rebuilt empty by the next process, so every incident waiting on approval would
silently disappear. The checkpoint DB therefore lives next to the audit DB in
``backend/data/`` — one directory to persist, one to back up.
"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from backend.graph.nodes import (
    approval_node,
    intake_node,
    notify_node,
    rca_node,
    route_after_approval,
    route_after_triage,
    triage_node,
)
from backend.graph.state import IncidentState

_DB_PATH = Path(__file__).parent.parent / "data" / "checkpoints.db"


def get_checkpointer(db_path: Path | None = None) -> SqliteSaver:
    """Open the durable checkpointer, creating ``backend/data/`` if needed.

    ``check_same_thread=False`` because uvicorn resolves an approval on a
    different worker thread than the one that started the run; sqlite3 is
    built in serialized threading mode, so the shared connection is safe.
    """
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Compile the playbook graph.

    Defaults to the on-disk checkpointer. Pass ``MemorySaver()`` for an
    ephemeral graph that leaves nothing behind (tests).
    """
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
        checkpointer=checkpointer or get_checkpointer(),
        interrupt_before=["approval"],
    )


def resume_after_approval(graph, config: dict, decision: dict) -> None:
    """Write the human decision into the checkpoint, then resume the paused run.

    A static ``interrupt_before`` is resumed by invoking with ``None`` input.
    Passing the decision as input instead would start a *fresh* run from
    ``intake`` that re-triages the incident and parks at the gate again, so
    ``notify`` would never fire and the approval would be silently dropped.

    Raises ``ValueError`` if the thread is not actually sitting at the gate — an
    unknown or already-resolved run_id has no approval to grant, and resuming it
    would start a new run rather than continue one.
    """
    state = graph.get_state(config)
    if "approval" not in (state.next or () if state else ()):
        raise ValueError("run is not awaiting approval")

    graph.update_state(config, decision)
    graph.invoke(None, config=config)


app = build_graph()
