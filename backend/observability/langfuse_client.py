"""Langfuse observability — wraps all LLM calls with trace/span context."""
import logging
from backend.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

logger = logging.getLogger(__name__)


def get_callback_handler(trace_name: str, metadata: dict = None):
    """Returns a LangChain callback handler that auto-traces all LLM calls.
    Falls back gracefully if Langfuse is not configured."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.info("Langfuse not configured — skipping observability.")
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
            trace_name=trace_name,
        )
    except Exception as e:
        logger.warning(f"Langfuse callback handler failed: {e}")
        return None


def flush():
    """Flush all pending traces to Langfuse."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return
    try:
        from langfuse import Langfuse
        Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        ).flush()
    except Exception as e:
        logger.warning(f"Langfuse flush failed: {e}")
