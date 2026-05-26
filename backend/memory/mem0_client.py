"""Mem0 memory client — stores and retrieves past incident context across runs."""
from mem0 import MemoryClient
from backend.config import MEM0_API_KEY

_client = None


def get_client() -> MemoryClient:
    global _client
    if _client is None:
        if not MEM0_API_KEY:
            raise RuntimeError(
                "MEM0_API_KEY is not set. Add it to your .env file."
            )
        _client = MemoryClient(api_key=MEM0_API_KEY)
    return _client


def search_similar_incidents(description: str, limit: int = 3) -> list[dict]:
    """Query memory for past incidents similar to the current one."""
    client = get_client()
    results = client.search(description, user_id="incident-agent", limit=limit)
    return results


def store_resolved_incident(incident_id: str, summary: dict) -> None:
    """Persist a resolved incident's details for future RCA reference."""
    client = get_client()
    memory_text = (
        f"Incident {incident_id}: {summary.get('title')}\n"
        f"Severity: {summary.get('severity')}\n"
        f"Affected Systems: {', '.join(summary.get('affected_systems', []))}\n"
        f"Root Cause: {summary.get('root_cause')}\n"
        f"Fix: {summary.get('recommended_fix')}"
    )
    client.add(memory_text, user_id="incident-agent")
