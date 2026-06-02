from langchain_core.messages import SystemMessage, HumanMessage
from backend.memory.mem0_client import search_similar_incidents
from backend.agents.llm_factory import get_llm

llm = get_llm()

SYSTEM_PROMPT = """You are an incident triage agent. Analyze the incident and:
1. Assign severity: P1 (critical/outage), P2 (major degradation), P3 (minor), P4 (low)
2. List affected systems
3. Write brief triage notes

Respond in JSON with keys: severity, affected_systems (list), triage_notes."""


def run_triage(state: dict) -> dict:
    similar = search_similar_incidents(state["description"])

    _MAX_MEMORY_CHARS = 500
    context = ""
    if similar:
        context = "\n\nSimilar past incidents for context:\n"
        for s in similar:
            entry = s.get("memory", "")[:_MAX_MEMORY_CHARS]
            context += f"- {entry}\n"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Incident: {state['title']}\n"
                f"Description: {state['description']}\n"
                f"{context}"
            )
        ),
    ]

    response = llm.invoke(messages)

    import json, re
    raw = response.content
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group()) if match else {}

    return {
        "severity": parsed.get("severity", "P3"),
        "affected_systems": parsed.get("affected_systems", []),
        "triage_notes": parsed.get("triage_notes", raw),
        "similar_incidents": similar,
        "messages": [response],
    }
