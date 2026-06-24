from functools import lru_cache

from backend.config import GEMINI_API_KEY, LLM_PROVIDER, OPENAI_API_KEY


def get_llm(temperature: float = 0):
    """Construct an LLM client for the configured provider.

    This is intentionally NOT called at import time. Building a client eagerly
    at module load forces an API key to be present just to import the package,
    which breaks tests and CI. Agents should fetch the client lazily via
    ``get_cached_llm()`` so the app can be imported without credentials.
    """
    if LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="gpt-4o",
            api_key=OPENAI_API_KEY,
            temperature=temperature,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
    )


@lru_cache(maxsize=1)
def get_cached_llm():
    """Return a process-wide singleton LLM client, built on first use."""
    return get_llm()
