"""Central configuration loaded from environment variables.

All secrets are read from the environment (or a local ``.env`` file). Nothing is
hardcoded. ``validate_config`` is called at API startup to fail fast on an
obviously broken configuration and to surface security-relevant warnings.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
MEM0_API_KEY = os.getenv("MEM0_API_KEY")
JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

_SUPPORTED_PROVIDERS = {"gemini", "openai"}


def validate_config() -> list[str]:
    """Validate configuration at startup.

    Returns a list of human-readable warnings (non-fatal). Raises
    ``RuntimeError`` for misconfiguration that would make the service
    unrunnable, so the process fails fast instead of erroring on first request.
    """
    warnings: list[str] = []

    if LLM_PROVIDER not in _SUPPORTED_PROVIDERS:
        raise RuntimeError(
            f"LLM_PROVIDER='{LLM_PROVIDER}' is not supported. "
            f"Choose one of: {sorted(_SUPPORTED_PROVIDERS)}."
        )

    if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
        raise RuntimeError(
            "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set. "
            "Set it in your environment or .env file."
        )
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise RuntimeError(
            "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
            "Set it in your environment or .env file."
        )

    if not API_KEY:
        warnings.append(
            "API_KEY is not set — endpoint authentication is DISABLED. "
            "Set API_KEY before exposing this service beyond localhost."
        )

    if bool(LANGFUSE_PUBLIC_KEY) != bool(LANGFUSE_SECRET_KEY):
        warnings.append(
            "Only one of LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY is set — "
            "observability will be skipped. Set both or neither."
        )

    for w in warnings:
        logger.warning(w)

    return warnings
