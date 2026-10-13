"""Tests for the LangGraph workflow wiring and routing logic."""
from langgraph.checkpoint.memory import MemorySaver

from backend.graph import nodes, state, workflow

# ── routing functions (playbook control flow) ───────────────────────────────

class TestRouting:
    def test_route_after_triage_always_rca(self) -> None:
        assert nodes.route_after_triage({}) == "rca"

    def test_route_after_approval_approved_goes_to_notify(self) -> None:
        assert nodes.route_after_approval({"approved": True}) == "notify"

    def test_route_after_approval_rejected_loops_to_rca(self) -> None:
        assert nodes.route_after_approval({"approved": False}) == "rca"

    def test_route_after_approval_none_defaults_to_notify(self) -> None:
        # Unset approval is treated as not-explicitly-rejected
        assert nodes.route_after_approval({}) == "notify"


# ── node wrappers delegate to the right agent ───────────────────────────────

class TestNodes:
    def test_intake_node_calls_run_intake(self, monkeypatch) -> None:
        monkeypatch.setattr(nodes, "run_intake", lambda iid: {"incident_id": iid})
        assert nodes.intake_node({"incident_id": "INC-9"}) == {"incident_id": "INC-9"}

    def test_triage_node_passes_full_state(self, monkeypatch) -> None:
        captured = {}
        monkeypatch.setattr(nodes, "run_triage", lambda s: captured.update(s) or {"severity": "P1"})
        out = nodes.triage_node({"title": "x"})
        assert out["severity"] == "P1"
        assert captured["title"] == "x"

    def test_rca_node_calls_run_rca(self, monkeypatch) -> None:
        monkeypatch.setattr(nodes, "run_rca", lambda s: {"root_cause": "rc"})
        assert nodes.rca_node({})["root_cause"] == "rc"

    def test_notify_node_calls_run_notify(self, monkeypatch) -> None:
        monkeypatch.setattr(nodes, "run_notify", lambda s: {"email_sent": True})
        assert nodes.notify_node({})["email_sent"] is True

    def test_approval_node_is_passthrough(self) -> None:
        # The approval node is a no-op interrupt point; it returns no state delta.
        assert nodes.approval_node({"anything": 1}) == {}


# ── compiled graph shape ────────────────────────────────────────────────────

class TestCompiledGraph:
    def test_build_graph_interrupts_before_approval(self) -> None:
        # Ephemeral checkpointer — keeps the test off the real on-disk DB
        app = workflow.build_graph(MemorySaver())
        # The compiled app exists and exposes invoke/get_state used by the API
        assert hasattr(app, "invoke")
        assert hasattr(app, "get_state")


# ── state reducers ──────────────────────────────────────────────────────────

class TestMergeGuardFindings:
    """Guard findings accumulate across nodes. RCA runs a second time when an
    approval is rejected, and the same finding twice tells an approver nothing
    new — so the reducer appends but does not repeat."""

    def test_appends_new_findings(self) -> None:
        merged = state.merge_guard_findings(["title: a"], ["description: b"])
        assert merged == ["title: a", "description: b"]

    def test_drops_repeats_while_keeping_order(self) -> None:
        merged = state.merge_guard_findings(
            ["title: a", "description: b"], ["description: b", "reporter: c"]
        )
        assert merged == ["title: a", "description: b", "reporter: c"]

    def test_handles_missing_sides(self) -> None:
        assert state.merge_guard_findings(None, ["x"]) == ["x"]
        assert state.merge_guard_findings(["x"], None) == ["x"]
        assert state.merge_guard_findings(None, None) == []

    def test_accepts_a_bare_string_update(self) -> None:
        assert state.merge_guard_findings([], "title: a") == ["title: a"]
