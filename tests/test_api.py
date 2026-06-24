"""Tests for FastAPI input validators and safe-state logic (no LLM / graph calls)."""
import pytest
from pydantic import ValidationError

# ── Import models directly to avoid triggering the full graph at module import ──
from backend.api.main import ApprovalRequest, IncidentRequest, _safe_state

# ── IncidentRequest validator ─────────────────────────────────────────────

class TestIncidentRequestValidator:
    def test_valid_incident_id(self) -> None:
        req = IncidentRequest(incident_id="INC-101")
        assert req.incident_id == "INC-101"

    def test_strips_whitespace_and_uppercases(self) -> None:
        req = IncidentRequest(incident_id="  inc-202  ")
        assert req.incident_id == "INC-202"

    def test_rejects_no_dash(self) -> None:
        with pytest.raises(ValidationError):
            IncidentRequest(incident_id="INC101")

    def test_rejects_letters_in_number_part(self) -> None:
        with pytest.raises(ValidationError):
            IncidentRequest(incident_id="INC-ABC")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValidationError):
            IncidentRequest(incident_id="")

    def test_rejects_plain_number(self) -> None:
        with pytest.raises(ValidationError):
            IncidentRequest(incident_id="12345")

    def test_valid_with_multi_letter_prefix(self) -> None:
        req = IncidentRequest(incident_id="INFRA-999")
        assert req.incident_id == "INFRA-999"

    def test_optional_recipients_defaults_to_none(self) -> None:
        req = IncidentRequest(incident_id="INC-1")
        assert req.recipients is None

    def test_valid_email_recipients(self) -> None:
        req = IncidentRequest(incident_id="INC-1", recipients=["a@example.com"])
        assert req.recipients is not None
        assert len(req.recipients) == 1

    def test_invalid_email_recipient_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IncidentRequest(incident_id="INC-1", recipients=["not-an-email"])


# ── ApprovalRequest validator ─────────────────────────────────────────────

class TestApprovalRequestValidator:
    def test_valid_approval(self) -> None:
        req = ApprovalRequest(approved=True, approver="Alice Chen")
        assert req.approved is True
        assert req.approver == "Alice Chen"

    def test_valid_rejection(self) -> None:
        req = ApprovalRequest(approved=False, approver="Bob")
        assert req.approved is False

    def test_approver_stripped(self) -> None:
        req = ApprovalRequest(approved=True, approver="  Carol  ")
        assert req.approver == "Carol"

    def test_approver_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalRequest(approved=True, approver="A" * 101)

    def test_approver_invalid_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalRequest(approved=True, approver="<script>")

    def test_approver_allows_email_format(self) -> None:
        req = ApprovalRequest(approved=True, approver="alice@company.com")
        assert req.approver == "alice@company.com"

    def test_approver_allows_hyphen_and_dot(self) -> None:
        req = ApprovalRequest(approved=True, approver="Mary-Jane O'Brien")
        assert "O'Brien" in req.approver

    def test_notes_optional_defaults_empty(self) -> None:
        req = ApprovalRequest(approved=True, approver="Dave")
        assert req.notes == ""

    def test_notes_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalRequest(approved=True, approver="Dave", notes="x" * 501)

    def test_notes_strips_control_chars(self) -> None:
        # Null bytes and other control chars should be stripped
        req = ApprovalRequest(approved=True, approver="Dave", notes="good\x00note\x1f")
        assert "\x00" not in req.notes
        assert "\x1f" not in req.notes
        assert "goodnote" in req.notes

    def test_notes_preserves_newline(self) -> None:
        # \n (0x0a) is NOT in the strip range, so it survives
        req = ApprovalRequest(approved=True, approver="Dave", notes="line1\nline2")
        assert "\n" in req.notes


# ── _safe_state allowlist ─────────────────────────────────────────────────

class TestSafeState:
    # These should NEVER reach the browser
    _INTERNAL_KEYS = ["messages", "similar_incidents", "notification_recipients"]
    _SAFE_KEYS = [
        "incident_id", "title", "severity", "description", "reporter",
        "affected_systems", "triage_notes", "root_cause", "rca_summary",
        "log_evidence", "recommended_fix", "approved", "approver",
        "approval_notes", "email_sent",
    ]

    def test_safe_keys_pass_through(self) -> None:
        values = {k: f"val-{k}" for k in self._SAFE_KEYS}
        result = _safe_state(values)
        assert set(result.keys()) == set(self._SAFE_KEYS)

    def test_internal_keys_stripped(self) -> None:
        values = {k: ["secret"] for k in self._INTERNAL_KEYS}
        result = _safe_state(values)
        assert result == {}

    def test_mixed_values_only_safe_returned(self) -> None:
        values = {
            "incident_id": "INC-1",
            "severity": "P2",
            "messages": [{"role": "user", "content": "prompt text"}],
            "notification_recipients": ["alice@example.com"],
        }
        result = _safe_state(values)
        assert "incident_id" in result
        assert "severity" in result
        assert "messages" not in result
        assert "notification_recipients" not in result

    def test_unknown_key_stripped(self) -> None:
        values = {"incident_id": "INC-1", "secret_token": "abc123"}
        result = _safe_state(values)
        assert "secret_token" not in result
        assert "incident_id" in result

    def test_empty_dict_returns_empty(self) -> None:
        assert _safe_state({}) == {}
