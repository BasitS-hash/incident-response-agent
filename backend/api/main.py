"""FastAPI backend — exposes LangGraph workflow over HTTP with AG-UI SSE streaming."""
import json
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.graph.workflow import app as graph_app
from backend.memory.mem0_client import search_similar_incidents
from backend.observability.langfuse_client import get_callback_handler, flush

api = FastAPI(title="Incident Response Agent API")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── AG-UI event helpers ──────────────────────────────────────────────
def sse_event(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


# ── Request / Response models ────────────────────────────────────────
class IncidentRequest(BaseModel):
    incident_id: str
    recipients: Optional[list[str]] = None


class ApprovalRequest(BaseModel):
    approved: bool
    approver: str
    notes: Optional[str] = ""


# ── Routes ───────────────────────────────────────────────────────────
@api.post("/incident")
async def start_incident(req: IncidentRequest):
    """Start a new incident workflow run. Returns run_id for streaming/approval."""
    run_id = str(uuid.uuid4())
    thread_config = {"configurable": {"thread_id": run_id}}

    initial_state = {
        "incident_id": req.incident_id,
        "title": "",
        "description": "",
        "reporter": "",
        "created_at": "",
        "severity": None,
        "affected_systems": [],
        "triage_notes": None,
        "similar_incidents": [],
        "root_cause": None,
        "rca_summary": None,
        "log_evidence": [],
        "recommended_fix": None,
        "approved": None,
        "approver": None,
        "approval_notes": None,
        "email_sent": False,
        "notification_recipients": req.recipients or [],
        "messages": [],
    }

    lf_handler = get_callback_handler(
        trace_name=f"incident-{req.incident_id}",
        metadata={"incident_id": req.incident_id, "run_id": run_id},
    )

    graph_app.invoke(
        initial_state,
        config={**thread_config, "callbacks": [lf_handler]},
    )
    flush()

    state = graph_app.get_state(thread_config)
    return {
        "run_id": run_id,
        "status": "awaiting_approval",
        "state": {
            k: v for k, v in state.values.items()
            if k != "messages"
        },
    }


@api.get("/stream/{run_id}")
async def stream_incident(run_id: str):
    """SSE endpoint — streams AG-UI events for the given run."""
    thread_config = {"configurable": {"thread_id": run_id}}

    async def event_generator():
        try:
            state = graph_app.get_state(thread_config)
            if not state:
                yield sse_event("RUN_ERROR", {"message": "Run not found"})
                return

            yield sse_event("RUN_STARTED", {"run_id": run_id})

            values = {k: v for k, v in state.values.items() if k != "messages"}
            yield sse_event("STATE_SNAPSHOT", {"state": values})

            next_nodes = list(state.next) if state.next else []
            if "approval" in next_nodes:
                yield sse_event("AWAITING_APPROVAL", {
                    "run_id": run_id,
                    "rca_summary": state.values.get("rca_summary"),
                    "severity": state.values.get("severity"),
                    "root_cause": state.values.get("root_cause"),
                    "recommended_fix": state.values.get("recommended_fix"),
                })

            yield sse_event("RUN_FINISHED", {"run_id": run_id})

        except Exception as e:
            yield sse_event("RUN_ERROR", {"message": str(e)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@api.post("/approve/{run_id}")
async def approve_incident(run_id: str, req: ApprovalRequest):
    """HITL endpoint — resumes the graph after human review."""
    thread_config = {"configurable": {"thread_id": run_id}}

    state = graph_app.get_state(thread_config)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    lf_handler = get_callback_handler(
        trace_name=f"approval-{run_id}",
        metadata={"run_id": run_id, "approved": req.approved},
    )

    graph_app.invoke(
        {
            "approved": req.approved,
            "approver": req.approver,
            "approval_notes": req.notes,
        },
        config={**thread_config, "callbacks": [lf_handler]},
    )
    flush()

    final_state = graph_app.get_state(thread_config)
    return {
        "run_id": run_id,
        "status": "completed" if req.approved else "rejected",
        "email_sent": final_state.values.get("email_sent", False),
    }


@api.get("/incidents/search")
async def search_incidents(q: str):
    """Search past resolved incidents from Mem0 memory."""
    results = search_similar_incidents(q)
    return {"results": results}


@api.get("/health")
async def health():
    return {"status": "ok"}
