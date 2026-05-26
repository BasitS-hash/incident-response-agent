"""Mem0 memory client — stores and retrieves past incident context across runs."""
import logging
from backend.config import MEM0_API_KEY

logger = logging.getLogger(__name__)
_client = None


def get_client():
    global _client
    if _client is None:
        if not MEM0_API_KEY:
            return None
        try:
            from mem0 import MemoryClient
            _client = MemoryClient(api_key=MEM0_API_KEY)
        except Exception as e:
            logger.warning(f"Mem0 client init failed: {e}")
            return None
    return _client


def search_similar_incidents(description: str, limit: int = 3) -> list[dict]:
    """Query memory for past incidents similar to the current one."""
    client = get_client()
    if not client:
        return []
    try:
        return client.search(description, user_id="incident-agent", limit=limit)
    except Exception as e:
        logger.warning(f"Mem0 search failed: {e}")
        return []


def store_resolved_incident(incident_id: str, summary: dict) -> None:
    """Persist a resolved incident's details for future RCA reference."""
    client = get_client()
    if not client:
        return
    try:
        memory_text = (
            f"Incident {incident_id}: {summary.get('title')}\n"
            f"Severity: {summary.get('severity')}\n"
            f"Affected Systems: {', '.join(summary.get('affected_systems', []))}\n"
            f"Root Cause: {summary.get('root_cause')}\n"
            f"Fix: {summary.get('recommended_fix')}"
        )
        client.add(memory_text, user_id="incident-agent")
    except Exception as e:
        logger.warning(f"Mem0 store failed: {e}")
