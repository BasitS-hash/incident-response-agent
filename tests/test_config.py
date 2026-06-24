"""Tests for startup configuration validation."""
import importlib

import pytest


def _reload_config(monkeypatch: pytest.MonkeyPatch, env: dict):
    """Reload backend.config with a controlled environment."""
    for key in [
        "API_KEY", "LLM_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import backend.config as config
    return importlib.reload(config)


class TestValidateConfig:
    def test_gemini_without_key_raises(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "gemini"})
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            config.validate_config()

    def test_openai_without_key_raises(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "openai"})
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            config.validate_config()

    def test_unsupported_provider_raises(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "llama", "GEMINI_API_KEY": "k"})
        with pytest.raises(RuntimeError, match="not supported"):
            config.validate_config()

    def test_valid_gemini_returns_warnings_list(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k"})
        warnings = config.validate_config()
        assert isinstance(warnings, list)

    def test_missing_api_key_produces_auth_warning(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k"})
        warnings = config.validate_config()
        assert any("authentication is DISABLED" in w for w in warnings)

    def test_api_key_set_no_auth_warning(self, monkeypatch) -> None:
        config = _reload_config(
            monkeypatch,
            {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k", "API_KEY": "secret"},
        )
        warnings = config.validate_config()
        assert not any("authentication is DISABLED" in w for w in warnings)

    def test_partial_langfuse_config_warns(self, monkeypatch) -> None:
        config = _reload_config(
            monkeypatch,
            {
                "LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k", "API_KEY": "s",
                "LANGFUSE_PUBLIC_KEY": "pub",  # secret intentionally omitted
            },
        )
        warnings = config.validate_config()
        assert any("LANGFUSE" in w for w in warnings)

    def test_provider_is_lowercased(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {"LLM_PROVIDER": "OpenAI", "OPENAI_API_KEY": "k"})
        assert config.LLM_PROVIDER == "openai"


@pytest.fixture(autouse=True)
def _restore_config():
    """Reload config from the real environment after each test in this module."""
    yield
    import backend.config as config
    importlib.reload(config)
