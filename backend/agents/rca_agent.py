import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agents.llm_factory import get_cached_llm
from backend.mcp_server.tools.log_tools import (
    get_deployment_history,
    get_system_metrics,
    query_system_logs,
)
from backend.security.untrusted import DATA_BOUNDARY_NOTE, wrap_untrusted_fields

SYSTEM_PROMPT = f"""You are a senior SRE performing root cause analysis. You will be given:
- Incident details and severity
- Recent error logs
- System metrics
- Recent deployment history

Identify the root cause and recommend a fix.
Respond ONLY with a flat JSON object. All values must be plain strings or a list of strings.
Do NOT use nested objects or arrays of objects.
Keys: root_cause (string), rca_summary (string), log_evidence (list of strings), recommended_fix (string).

{DATA_BOUNDARY_NOTE}"""


def run_rca(state: dict) -> dict:
    systems = state.get("affected_systems", ["unknown-service"])
    primary_service = systems[0] if systems else "unknown-service"

    logs = query_system_logs(primary_service)
    metrics = get_system_metrics(primary_service)
    deployments = get_deployment_history(primary_service)

    # This is the prompt that produces the RCA a human is asked to approve, so
    # it is the one an injected instruction would most want to steer.
    guarded = wrap_untrusted_fields({
        "title":       state["title"],
        "description": state["description"],
    })

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Severity: {state['severity']}\n\n"
                f"{guarded.text}\n\n"
                f"Logs (last 30m):\n" + "\n".join(logs) + "\n\n"
                f"Metrics: {metrics}\n\n"
                f"Recent Deployments: {deployments}"
            )
        ),
    ]

    response = get_cached_llm().invoke(messages)

    raw = response.content
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = json.loads(match.group()) if match else {}

    def _str(val, fallback=""):
        if val is None:
            return fallback
        if isinstance(val, dict):
            return json.dumps(val)
        if isinstance(val, list):
            return "; ".join(str(v) for v in val)
        return str(val)

    return {
        "root_cause": _str(parsed.get("root_cause"), "Unable to determine"),
        "rca_summary": _str(parsed.get("rca_summary"), raw),
        "log_evidence": parsed.get("log_evidence", logs[:3]),
        "recommended_fix": _str(parsed.get("recommended_fix")),
        "input_guard_findings": list(guarded.findings),
        "messages": [response],
    }
