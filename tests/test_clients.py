"""Tests for the Mem0 and Langfuse client wrappers.

Focus: graceful degradation. When the services are not configured or raise,
the wrappers must never crash the incident workflow.
"""
from backend.memory import mem0_client
from backend.observability import langfuse_client

# ── mem0_client ─────────────────────────────────────────────────────────────

class TestMem0Client:
    def test_get_client_none_without_key(self, monkeypatch) -> None:
        monkeypatch.setattr(mem0_client, "_client", None)
        monkeypatch.setattr(mem0_client, "MEM0_API_KEY", None)
        assert mem0_client.get_client() is None

    def test_search_returns_empty_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(mem0_client, "get_client", lambda: None)
        assert mem0_client.search_similar_incidents("anything") == []

    def test_search_returns_client_results(self, monkeypatch) -> None:
        class _Client:
            def search(self, q, user_id, limit):
                return [{"memory": "hit"}]

        monkeypatch.setattr(mem0_client, "get_client", lambda: _Client())
        results = mem0_client.search_similar_incidents("redis")
        assert results == [{"memory": "hit"}]

    def test_search_swallows_client_error(self, monkeypatch) -> None:
        class _Client:
            def search(self, *a, **k):
                raise RuntimeError("boom")

        monkeypatch.setattr(mem0_client, "get_client", lambda: _Client())
        assert mem0_client.search_similar_incidents("x") == []

    def test_store_noop_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(mem0_client, "get_client", lambda: None)
        # Should not raise
        mem0_client.store_resolved_incident("INC-1", {"title": "t"})

    def test_store_swallows_client_error(self, monkeypatch) -> None:
        class _Client:
            def add(self, *a, **k):
                raise RuntimeError("boom")

        monkeypatch.setattr(mem0_client, "get_client", lambda: _Client())
        mem0_client.store_resolved_incident("INC-1", {"title": "t", "affected_systems": []})


# ── langfuse_client ─────────────────────────────────────────────────────────

class TestLangfuseClient:
    def test_handler_none_without_keys(self, monkeypatch) -> None:
        monkeypatch.setattr(langfuse_client, "LANGFUSE_PUBLIC_KEY", None)
        monkeypatch.setattr(langfuse_client, "LANGFUSE_SECRET_KEY", None)
        assert langfuse_client.get_callback_handler("trace") is None

    def test_flush_noop_without_keys(self, monkeypatch) -> None:
        monkeypatch.setattr(langfuse_client, "LANGFUSE_PUBLIC_KEY", None)
        monkeypatch.setattr(langfuse_client, "LANGFUSE_SECRET_KEY", None)
        # Should not raise
        langfuse_client.flush()

    def test_warns_on_insecure_remote_host(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(langfuse_client, "LANGFUSE_HOST", "http://traces.example.com")
        with caplog.at_level("WARNING"):
            langfuse_client._warn_if_insecure_host()
        assert any("unencrypted" in r.message for r in caplog.records)

    def test_no_warn_on_localhost_http(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(langfuse_client, "LANGFUSE_HOST", "http://localhost:3000")
        with caplog.at_level("WARNING"):
            langfuse_client._warn_if_insecure_host()
        assert not any("unencrypted" in r.message for r in caplog.records)

    def test_no_warn_on_https_remote(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(langfuse_client, "LANGFUSE_HOST", "https://traces.example.com")
        with caplog.at_level("WARNING"):
            langfuse_client._warn_if_insecure_host()
        assert not any("unencrypted" in r.message for r in caplog.records)
