import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.llm_factory import get_cached_llm
from backend.memory.mem0_client import search_similar_incidents
from backend.security.untrusted import DATA_BOUNDARY_NOTE, wrap_untrusted, wrap_untrusted_fields

SYSTEM_PROMPT = f"""You are an incident triage agent. Analyze the incident and:
1. Assign severity: P1 (critical/outage), P2 (major degradation), P3 (minor), P4 (low)
2. List affected systems
3. Write brief triage notes

Respond in JSON with keys: severity, affected_systems (list), triage_notes.

{DATA_BOUNDARY_NOTE}"""


def run_triage(state: dict) -> dict:
    similar = search_similar_incidents(state["description"])

    _MAX_MEMORY_CHARS = 500
    context = ""
    findings: list[str] = []
    if similar:
        context = "\n\nSimilar past incidents for context:\n"
        for s in similar:
            # Mem0 entries are summaries of earlier incidents, so they carry the
            # same reporter-written text forward across runs. The 500-char cap
            # stays as the ceiling for a recalled entry.
            entry = wrap_untrusted("memory", s.get("memory", ""), max_chars=_MAX_MEMORY_CHARS)
            context += f"{entry.text}\n"
            findings.extend(entry.findings)

    # The title and description on state came back from the intake model, which
    # echoes the ticket text. Intake wrapping them does not help here — this is
    # a separate prompt and has to re-establish the boundary itself.
    guarded = wrap_untrusted_fields({
        "title":       state["title"],
        "description": state["description"],
    })
    findings.extend(guarded.findings)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"{guarded.text}{context}"),
    ]

    response = get_cached_llm().invoke(messages)

    raw = response.content
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group()) if match else {}

    return {
        "severity": parsed.get("severity", "P3"),
        "affected_systems": parsed.get("affected_systems", []),
        "triage_notes": parsed.get("triage_notes", raw),
        "similar_incidents": similar,
        "input_guard_findings": findings,
        "messages": [response],
    }
