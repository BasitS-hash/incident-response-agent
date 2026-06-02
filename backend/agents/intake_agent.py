import json
import re
from langchain_core.messages import SystemMessage, HumanMessage
from backend.mcp_server.tools.jira_tools import get_jira_incident
from backend.agents.llm_factory import get_llm

llm = get_llm()

SYSTEM_PROMPT = """You are an incident intake agent. Your job is to parse a Jira
incident and extract structured fields. Always respond with ONLY valid JSON (no
markdown fences) with keys: incident_id, title, description, reporter, created_at."""


def _parse_llm_json(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


def run_intake(incident_id: str) -> dict:
    raw = get_jira_incident(incident_id)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Parse this incident:\n{json.dumps(raw)}"),
    ]

    response = llm.invoke(messages)

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
        "messages": messages + [response],
    }
