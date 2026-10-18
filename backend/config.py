"""Central configuration loaded from environment variables.

All secrets are read from the environment (or a local ``.env`` file). Nothing is
hardcoded. ``validate_config`` is called at API startup to fail fast on an
obviously broken configuration and to surface security-relevant warnings.
"""
import logging
import os

from dotenv import load_dotenv

from backend.security.principals import parse_api_keys

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "")
# Named keys: ``principal:scopes:key`` entries. The approver written into the
# audit row is derived from whichever of these authenticated the call, never
# from the request body — see backend/security/principals.py.
_API_KEYS = parse_api_keys(os.getenv("API_KEYS", ""))
API_PRINCIPALS = _API_KEYS.principals
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

    if _API_KEYS.errors:
        # Fail fast rather than start with a key configuration nobody can read.
        # A deployment that thinks it revoked a key and did not is worse off
        # than one that refuses to boot and says which entry is wrong.
        raise RuntimeError(
            "API_KEYS is malformed:\n  " + "\n  ".join(_API_KEYS.errors)
        )
    warnings.extend(_API_KEYS.warnings)

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

    if not API_KEY and not API_PRINCIPALS:
        warnings.append(
            "Neither API_KEY nor API_KEYS is set — endpoint authentication is "
            "DISABLED. Approvals are recorded against a principal that says so "
            "rather than against a person. Set API_KEYS before exposing this "
            "service beyond localhost."
        )
    elif not API_PRINCIPALS:
        warnings.append(
            "API_KEY is set but API_KEYS is not — the shared key names nobody, "
            "so POST /approve will be refused. Configure named keys to approve."
        )

    if bool(LANGFUSE_PUBLIC_KEY) != bool(LANGFUSE_SECRET_KEY):
        warnings.append(
            "Only one of LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY is set — "
            "observability will be skipped. Set both or neither."
        )

    for w in warnings:
        logger.warning(w)

    return warnings
