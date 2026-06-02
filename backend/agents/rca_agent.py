from langchain_core.messages import SystemMessage, HumanMessage
from backend.mcp_server.tools.log_tools import (
    query_system_logs,
    get_system_metrics,
    get_deployment_history,
)
from backend.agents.llm_factory import get_llm

llm = get_llm()

SYSTEM_PROMPT = """You are a senior SRE performing root cause analysis. You will be given:
- Incident details and severity
- Recent error logs
- System metrics
- Recent deployment history

Identify the root cause and recommend a fix.
Respond ONLY with a flat JSON object. All values must be plain strings or a list of strings.
Do NOT use nested objects or arrays of objects.
Keys: root_cause (string), rca_summary (string), log_evidence (list of strings), recommended_fix (string)."""


def run_rca(state: dict) -> dict:
    systems = state.get("affected_systems", ["unknown-service"])
    primary_service = systems[0] if systems else "unknown-service"

    logs = query_system_logs(primary_service)
    metrics = get_system_metrics(primary_service)
    deployments = get_deployment_history(primary_service)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Incident: {state['title']}\n"
                f"Severity: {state['severity']}\n"
                f"Description: {state['description']}\n\n"
                f"Logs (last 30m):\n" + "\n".join(logs) + "\n\n"
                f"Metrics: {metrics}\n\n"
                f"Recent Deployments: {deployments}"
            )
        ),
    ]

    response = llm.invoke(messages)

    import json, re
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
        "messages": [response],
    }
