import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.llm_factory import get_cached_llm
from backend.mcp_server.tools.jira_tools import get_jira_incident
from backend.security.untrusted import DATA_BOUNDARY_NOTE, wrap_untrusted_fields

SYSTEM_PROMPT = f"""You are an incident intake agent. Your job is to parse a Jira
incident and extract structured fields. Always respond with ONLY valid JSON (no
markdown fences) with keys: incident_id, title, description, reporter, created_at.

{DATA_BOUNDARY_NOTE}"""


def _parse_llm_json(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


def run_intake(incident_id: str) -> dict:
    raw = get_jira_incident(incident_id)

    # Everything below is typed by whoever filed the ticket, so it is
    # attacker-controlled for anyone who can file one. The id is validated by the
    # API and created_at is ours, so those two go in as plain prompt text.
    guarded = wrap_untrusted_fields({
        "title":       raw["title"],
        "description": raw["description"],
        "reporter":    raw["reporter"],
        "status":      raw["status"],
        "priority":    raw["priority"],
    })

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Parse this incident.\n"
                f"incident_id: {raw['id']}\n"
                f"created_at: {raw['created_at']}\n\n"
                f"{guarded.text}"
            )
        ),
    ]

    response = get_cached_llm().invoke(messages)

    try:
        parsed = _parse_llm_json(str(response.content))
    except (json.JSONDecodeError, AttributeError):
        parsed = {
            "incident_id": raw["id"],
            "title": raw["title"],
            "description": raw["description"],
            "reporter": raw["reporter"],
            "created_at": raw["created_at"],
        }

    return {
        "incident_id": parsed.get("incident_id", raw["id"]),
        "title": parsed.get("title", raw["title"]),
        "description": parsed.get("description", raw["description"]),
        "reporter": parsed.get("reporter", raw["reporter"]),
        "created_at": parsed.get("created_at", raw["created_at"]),
        "input_guard_findings": list(guarded.findings),
        "messages": messages + [response],
    }
