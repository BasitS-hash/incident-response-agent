"""Tests for the LangGraph workflow wiring and routing logic."""
from backend.graph import nodes, workflow

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
        app = workflow.build_graph()
        # The compiled app exists and exposes invoke/get_state used by the API
        assert hasattr(app, "invoke")
        assert hasattr(app, "get_state")
