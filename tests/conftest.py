"""Shared pytest fixtures and helpers.

The agents call out to an LLM and to external services (Mem0, Jira, SMTP).
These fixtures provide deterministic fakes so the core incident-response logic
(triage, enrichment, RCA, playbook routing) can be tested without network or
credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class FakeLLMResponse:
    """Mimics a LangChain message: exposes a ``.content`` attribute."""

    content: str


class FakeLLM:
    """A stand-in LLM whose ``invoke`` returns a queued or fixed response."""

    def __init__(self, content: str = "{}") -> None:
        self._content = content
        self.calls: list[Any] = []

    def invoke(self, messages: Any) -> FakeLLMResponse:
        self.calls.append(messages)
        return FakeLLMResponse(content=self._content)


@pytest.fixture
def fake_llm_factory(monkeypatch: pytest.MonkeyPatch):
    """Patch ``get_cached_llm`` in a target agent module with a FakeLLM.

    Usage::

        def test_x(fake_llm_factory):
            llm = fake_llm_factory("backend.agents.triage_agent", '{"severity": "P1"}')
    """

    def _install(module_path: str, content: str = "{}") -> FakeLLM:
        llm = FakeLLM(content=content)
        monkeypatch.setattr(module_path + ".get_cached_llm", lambda: llm)
        return llm

    return _install
