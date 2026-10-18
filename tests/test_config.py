"""Tests for startup configuration validation."""
import importlib

import pytest


def _reload_config(monkeypatch: pytest.MonkeyPatch, env: dict):
    """Reload backend.config with a controlled environment."""
    for key in [
        "API_KEY", "API_KEYS", "LLM_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY",
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


class TestNamedApiKeys:
    """``API_KEYS`` is what makes an approval attributable, so a config error
    here fails startup rather than being logged and shrugged off."""

    _GOOD = {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "k"}

    def test_named_keys_are_parsed_into_principals(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {
            **self._GOOD, "API_KEYS": "alice@corp.com:submit+approve:" + "k" * 24,
        })
        assert config.validate_config() is not None
        assert config.API_PRINCIPALS["k" * 24].name == "alice@corp.com"

    def test_malformed_named_keys_fail_startup(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {
            **self._GOOD, "API_KEYS": "alice:deploy:" + "k" * 24,
        })
        with pytest.raises(RuntimeError, match="API_KEYS"):
            config.validate_config()

    def test_startup_error_does_not_quote_key_material(self, monkeypatch) -> None:
        secret = "s3cret-nobody-should-see"
        config = _reload_config(monkeypatch, {
            **self._GOOD, "API_KEYS": "alice:deploy:" + secret,
        })
        with pytest.raises(RuntimeError) as exc:
            config.validate_config()
        assert secret not in str(exc.value)

    def test_named_keys_alone_turn_auth_on(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {
            **self._GOOD, "API_KEYS": "alice:approve:" + "k" * 24,
        })
        warnings = config.validate_config()
        assert not any("authentication is DISABLED" in w for w in warnings)

    def test_shared_key_without_named_keys_warns_approval_is_refused(
        self, monkeypatch
    ) -> None:
        config = _reload_config(monkeypatch, {**self._GOOD, "API_KEY": "shared"})
        warnings = config.validate_config()
        assert any("API_KEYS" in w and "approv" in w for w in warnings)

    def test_named_keys_present_means_no_approval_warning(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {
            **self._GOOD, "API_KEY": "shared",
            "API_KEYS": "alice:approve:" + "k" * 24,
        })
        warnings = config.validate_config()
        assert not any("approv" in w for w in warnings)

    def test_short_key_warning_is_surfaced_at_startup(self, monkeypatch) -> None:
        config = _reload_config(monkeypatch, {**self._GOOD, "API_KEYS": "alice:approve:x"})
        warnings = config.validate_config()
        assert any("entry 1" in w for w in warnings)


@pytest.fixture(autouse=True)
def _restore_config():
    """Reload config from the real environment after each test in this module."""
    yield
    import backend.config as config
    importlib.reload(config)
