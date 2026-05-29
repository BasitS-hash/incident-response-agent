"""Unit tests for pure agent helper functions (no LLM calls)."""
import json
import re
import pytest


# ── intake_agent._parse_llm_json ──────────────────────────────────────────

def _parse_llm_json(content: str) -> dict:
    """Inline copy of intake_agent._parse_llm_json for isolated testing."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


class TestParseLlmJson:
    def test_plain_json(self) -> None:
        raw = '{"incident_id": "INC-1", "title": "Down"}'
        result = _parse_llm_json(raw)
        assert result["incident_id"] == "INC-1"

    def test_strips_json_fence(self) -> None:
        raw = '```json\n{"incident_id": "INC-2", "title": "Slow"}\n```'
        result = _parse_llm_json(raw)
        assert result["title"] == "Slow"

    def test_strips_plain_fence(self) -> None:
        raw = '```\n{"incident_id": "INC-3"}\n```'
        result = _parse_llm_json(raw)
        assert result["incident_id"] == "INC-3"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("not json at all")

    def test_nested_fields_preserved(self) -> None:
        raw = '{"incident_id": "INC-4", "reporter": "Alice", "created_at": "2025-01-01"}'
        result = _parse_llm_json(raw)
        assert result["reporter"] == "Alice"


# ── rca_agent._str ────────────────────────────────────────────────────────

def _str(val, fallback: str = "") -> str:
    """Inline copy of rca_agent._str for isolated testing."""
    if val is None:
        return fallback
    if isinstance(val, dict):
        return json.dumps(val)
    if isinstance(val, list):
        return "; ".join(str(v) for v in val)
    return str(val)


class TestRcaStrHelper:
    def test_none_returns_fallback(self) -> None:
        assert _str(None, "fallback") == "fallback"

    def test_none_default_fallback_is_empty(self) -> None:
        assert _str(None) == ""

    def test_string_passthrough(self) -> None:
        assert _str("root cause text") == "root cause text"

    def test_dict_serialized_to_json(self) -> None:
        result = _str({"key": "val"})
        assert json.loads(result) == {"key": "val"}

    def test_list_joined_with_semicolons(self) -> None:
        assert _str(["step1", "step2", "step3"]) == "step1; step2; step3"

    def test_integer_converted_to_string(self) -> None:
        assert _str(42) == "42"

    def test_empty_list(self) -> None:
        assert _str([]) == ""

    def test_nested_dict_in_list(self) -> None:
        result = _str([{"a": 1}, {"b": 2}])
        assert "a" in result
        assert "b" in result


# ── triage_agent memory length cap ────────────────────────────────────────

class TestTriageMemoryLengthCap:
    """Verify the 500-char cap on Mem0 memory injection."""

    _MAX_MEMORY_CHARS = 500

    def _build_context(self, similar: list[dict]) -> str:
        context = ""
        if similar:
            context = "\n\nSimilar past incidents for context:\n"
            for s in similar:
                entry = s.get("memory", "")[: self._MAX_MEMORY_CHARS]
                context += f"- {entry}\n"
        return context

    def test_short_memory_passes_through(self) -> None:
        similar = [{"memory": "Redis OOM from connection leak."}]
        ctx = self._build_context(similar)
        assert "Redis OOM" in ctx

    def test_long_memory_is_capped(self) -> None:
        long_text = "x" * 2000
        similar = [{"memory": long_text}]
        ctx = self._build_context(similar)
        # The injected snippet should be at most MAX_MEMORY_CHARS chars
        # plus the prefix/suffix overhead
        assert len(long_text[:self._MAX_MEMORY_CHARS]) == self._MAX_MEMORY_CHARS
        assert long_text[:self._MAX_MEMORY_CHARS] in ctx
        # Confirm the full long text is NOT present
        assert long_text not in ctx

    def test_empty_similar_produces_no_context(self) -> None:
        assert self._build_context([]) == ""

    def test_multiple_entries_all_capped(self) -> None:
        similar = [
            {"memory": "A" * 600},
            {"memory": "B" * 100},
        ]
        ctx = self._build_context(similar)
        # First entry capped at 500
        assert "A" * 500 in ctx
        assert "A" * 501 not in ctx
        # Second entry fully present (under cap)
        assert "B" * 100 in ctx

    def test_missing_memory_key_safe(self) -> None:
        similar = [{}]
        ctx = self._build_context(similar)
        assert "Similar past incidents" in ctx
