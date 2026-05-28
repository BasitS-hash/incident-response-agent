"""FastAPI backend — exposes LangGraph workflow over HTTP with AG-UI SSE streaming."""
import json
import logging
import re
import uuid
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from backend.audit.log import init_db, record_run_started, record_run_completed, get_all_runs, get_run
from backend.config import API_KEY
from backend.graph.workflow import app as graph_app
from backend.memory.mem0_client import search_similar_incidents
from backend.observability.langfuse_client import get_callback_handler, flush

logger = logging.getLogger(__name__)

# ── Rate limiter ─────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

api = FastAPI(title="Incident Response Agent API")
api.state.limiter = limiter
api.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialise audit DB on startup (no-op if table already exists)
init_db()

api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# ── Security headers middleware ──────────────────────────────────────
@api.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ── API key auth ─────────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str = Security(_api_key_header)):
    """Protect state-changing POST endpoints with an API key.
    If API_KEY is not set in .env, auth is skipped (local dev mode)."""
    if not API_KEY:
        return  # dev mode — no key configured, allow all
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )


# ── AG-UI event helpers ──────────────────────────────────────────────
def sse_event(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


# ── Safe state keys sent to the frontend ────────────────────────────
_SAFE_STATE_KEYS = {
    "incident_id", "title", "severity", "description", "reporter",
    "affected_systems", "triage_notes", "root_cause", "rca_summary",
    "log_evidence", "recommended_fix", "approved", "approver",
    "approval_notes", "email_sent",
}


def _safe_state(values: dict) -> dict:
    """Return only the keys safe to expose to the browser."""
    return {k: v for k, v in values.items() if k in _SAFE_STATE_KEYS}


# ── Request / Response models ────────────────────────────────────────
class IncidentRequest(BaseModel):
    incident_id: str
    recipients: Optional[list[EmailStr]] = None

    @field_validator("incident_id")
    @classmethod
    def validate_incident_id(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]+-\d+$", v):
            raise ValueError("incident_id must match pattern INC-NNNN")
        return v


class ApprovalRequest(BaseModel):
    approved: bool
    approver: str
    notes: Optional[str] = ""

    @field_validator("approver")
    @classmethod
    def sanitize_approver(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 100:
            raise ValueError("approver name too long (max 100 chars)")
        if not re.match(r"^[\w\s.\-@']+$", v):
            raise ValueError("approver name contains invalid characters")
        return v

    @field_validator("notes")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> str:
        if not v:
            return ""
        v = v.strip()
        if len(v) > 500:
            raise ValueError("notes too long (max 500 chars)")
        # Strip control characters that could be used for prompt injection
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        return v


# ── Routes ───────────────────────────────────────────────────────────
@api.post("/incident", dependencies=[Security(verify_api_key)])
@limiter.limit("10/minute")
async def start_incident(request: Request, req: IncidentRequest):
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
        "notification_recipients": [str(r) for r in (req.recipients or [])],
        "messages": [],
    }

    lf_handler = get_callback_handler(
        trace_name=f"incident-{req.incident_id}",
        metadata={"incident_id": req.incident_id, "run_id": run_id},
    )

    callbacks = [lf_handler] if lf_handler else []
    graph_app.invoke(
        initial_state,
        config={**thread_config, "callbacks": callbacks},
    )
    flush()

    state = graph_app.get_state(thread_config)

    # Persist run to audit log
    record_run_started(run_id, req.incident_id, state.values if state else {})

    return {
        "run_id": run_id,
        "status": "awaiting_approval",
        "state": _safe_state(state.values),
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

            values = _safe_state(state.values)
            yield sse_event("STATE_SNAPSHOT", {"state": values})

            next_nodes = list(state.next) if state.next else []
            if "approval" in next_nodes:
                yield sse_event("AWAITING_APPROVAL", {
                    "run_id": run_id,
                    "rca_summary":     state.values.get("rca_summary"),
                    "severity":        state.values.get("severity"),
                    "root_cause":      state.values.get("root_cause"),
                    "recommended_fix": state.values.get("recommended_fix"),
                })

            yield sse_event("RUN_FINISHED", {"run_id": run_id})

        except Exception as e:
            logger.error("SSE stream error for run %s: %s", run_id, e, exc_info=True)
            yield sse_event("RUN_ERROR", {"message": "An internal error occurred."})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@api.post("/approve/{run_id}", dependencies=[Security(verify_api_key)])
@limiter.limit("20/minute")
async def approve_incident(request: Request, run_id: str, req: ApprovalRequest):
    """HITL endpoint — resumes the graph after human review."""
    thread_config = {"configurable": {"thread_id": run_id}}

    lf_handler = get_callback_handler(
        trace_name=f"approval-{run_id}",
        metadata={"run_id": run_id, "approved": req.approved},
    )

    callbacks = [lf_handler] if lf_handler else []
    try:
        graph_app.invoke(
            {
                "approved":       req.approved,
                "approver":       req.approver,
                "approval_notes": req.notes,
            },
            config={**thread_config, "callbacks": callbacks},
        )
    except Exception as e:
        # Graph may raise if notify step fails — still return success so modal closes
        logger.warning("[approve] graph invoke error (non-fatal): %s", type(e).__name__)

    flush()

    email_sent = False
    try:
        final_state = graph_app.get_state(thread_config)
        if final_state and final_state.values:
            email_sent = bool(final_state.values.get("email_sent", False))
            # Persist approval outcome to audit log
            record_run_completed(run_id, final_state.values)
    except Exception as e:
        logger.warning("[approve] get_state error (non-fatal): %s", type(e).__name__)

    return {
        "run_id":     run_id,
        "status":     "completed" if req.approved else "rejected",
        "email_sent": email_sent,
    }


@api.get("/incidents/search", dependencies=[Security(verify_api_key)])
async def search_incidents(q: str):
    """Search past resolved incidents from Mem0 memory."""
    results = search_similar_incidents(q)
    return {"results": results}


@api.get("/runs", dependencies=[Security(verify_api_key)])
async def list_runs(limit: int = 100):
    """Return audit log — all past incident runs newest first."""
    runs = get_all_runs(limit=max(1, min(limit, 500)))
    return {"runs": runs, "total": len(runs)}


@api.get("/runs/{run_id}", dependencies=[Security(verify_api_key)])
async def get_run_detail(run_id: str):
    """Return full audit detail for a single run."""
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@api.get("/health")
async def health():
    return {"status": "ok"}
