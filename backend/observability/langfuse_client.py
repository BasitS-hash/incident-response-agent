"""Langfuse observability — wraps all LLM calls with trace/span context."""
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from backend.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

_langfuse = None


def get_langfuse() -> Langfuse:
    global _langfuse
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
    return _langfuse


def get_callback_handler(trace_name: str, metadata: dict = None) -> CallbackHandler:
    """Returns a LangChain callback handler that auto-traces all LLM calls."""
    lf = get_langfuse()
    trace = lf.trace(name=trace_name, metadata=metadata or {})
    return CallbackHandler(trace_id=trace.id)


def flush():
    """Flush all pending traces to Langfuse — call at end of each workflow run."""
    get_langfuse().flush()
