# Incident Response Agent

An AI-powered incident response system that automates triage, root cause analysis, and on-call notification. Built with LangGraph, MCP, Mem0, Langfuse, and AG-UI.

---

## What It Does

When an incident fires, an SRE typically has to manually:
- Pull logs and metrics
- Figure out what changed (deployments, config)
- Write up a root cause analysis
- Notify the on-call team

This agent does all of that automatically — and pauses for human approval before sending any notifications.

**Alert fires → Agent investigates → Human approves → Team notified**

---

## The 5-Agent Workflow

```
Intake → Triage → RCA → Approval (HITL pause) → Notify
```

| Agent | What it does |
|-------|-------------|
| **Intake** | Fetches incident details from Jira (title, description, reporter, priority) |
| **Triage** | Assigns severity (P1–P4), identifies affected systems, adds triage notes |
| **RCA** | Queries logs, metrics, and deployment history — LLM identifies root cause and recommends a fix |
| **Approval** | Human-in-the-loop interrupt — workflow pauses until an authorized approver accepts or rejects |
| **Notify** | Sends email notification with full RCA summary to the on-call team |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Orchestration** | [LangGraph](https://langchain-ai.github.io/langgraph/) — stateful multi-agent workflow with SQLite checkpointing for HITL persistence |
| **Tools** | [MCP](https://modelcontextprotocol.io/) — modular tool server (Jira, logs, metrics, email) |
| **Memory** | [Mem0](https://mem0.ai/) — remembers past incidents and resolutions across runs |
| **Observability** | [Langfuse](https://langfuse.com/) — full LLM tracing, token usage, latency per agent |
| **Streaming** | [AG-UI](https://github.com/ag-ui-protocol/ag-ui) — SSE protocol for real-time frontend updates |
| **LLM** | Google Gemini 2.5 Flash via LangChain |
| **Backend** | FastAPI + uvicorn |
| **Frontend** | React 19 + TypeScript + Vite |

---

## Demo Incidents

| ID | Service | Issue | Severity |
|----|---------|-------|----------|
| `INC-101` | Auth service | Redis connection pool reduced by deployment → 97% cache miss rate → OOMKill | P1 |
| `INC-205` | Payment service | ORM migration didn't port connection pool config → PostgreSQL connection exhaustion | P2 |
| `INC-312` | Notification service | Marketing deploy accidentally applied unsubscribe logic to transactional emails → AWS SES suspended | P2 |

---

## Project Structure

```
incident-response-agent/
├── backend/
│   ├── agents/
│   │   ├── intake_agent.py       # Fetches incident from Jira
│   │   ├── triage_agent.py       # Assigns severity and affected systems
│   │   ├── rca_agent.py          # Root cause analysis via logs + LLM
│   │   └── notify_agent.py       # Sends email notification
│   ├── api/
│   │   └── main.py               # FastAPI routes + SSE streaming
│   ├── graph/
│   │   ├── workflow.py           # LangGraph graph definition
│   │   ├── nodes.py              # Node wrappers + routing logic
│   │   └── state.py              # IncidentState schema
│   ├── mcp_server/
│   │   └── tools/
│   │       ├── jira_tools.py     # Jira integration (mock → real via API token)
│   │       ├── log_tools.py      # Log/metrics/deployment data (mock → Splunk/Loki)
│   │       └── email_tools.py    # Email sending (mock → SMTP/SendGrid)
│   ├── memory/
│   │   └── mem0_client.py        # Mem0 for cross-run incident memory
│   ├── observability/
│   │   └── langfuse_client.py    # Langfuse tracing
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ChatUI.tsx             # Real-time chat event log
│       │   ├── WorkflowStepper.tsx    # Visual progress dots
│       │   ├── IncidentDetails.tsx    # Live state panel
│       │   └── HITLApprovalModal.tsx  # Human review modal
│       ├── hooks/
│       │   └── useAgentStream.ts      # SSE event consumer
│       └── api/
│           └── client.ts             # Axios API client
├── docker-compose.yml
└── start.sh
```

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 18+
- A `.env` file in `backend/` (see below)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.api.main:api --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

### Environment Variables (`.env` in project root)
```
# LLM
GEMINI_API_KEY=your_gemini_key

# API auth — leave blank to run in dev mode (no key required)
API_KEY=

# Jira (optional — mocked if not set)
JIRA_URL=https://yourorg.atlassian.net
JIRA_EMAIL=you@yourorg.com
JIRA_TOKEN=your_jira_api_token

# Email / SMTP (optional — mocked if not set)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password

# Observability (optional — graceful fallback if not set)
MEM0_API_KEY=your_mem0_key
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
```

---

## Swapping Mocks for Real Integrations

Everything is built with a clear swap point — the agent logic doesn't change, only the data source.

| Mock | Real integration | What to change |
|------|-----------------|----------------|
| Jira mock | Jira REST API | Add `JIRA_API_TOKEN` + `JIRA_BASE_URL` to `.env`, update `jira_tools.py` |
| Log mock | Splunk / Loki / Datadog | Replace `query_system_logs()` in `log_tools.py` |
| Email mock | SendGrid / SES / SMTP | Add credentials to `.env`, update `email_tools.py` |
| SQLite checkpointer | PostgreSQL | Swap `SqliteSaver` for `PostgresSaver` in `workflow.py` |

---

## Security

- POST endpoints protected by `X-API-Key` header (set `API_KEY` in `.env`; leave blank for dev mode)
- Input validation on all user-supplied fields — incident ID format enforced, approver name and notes sanitized against prompt injection
- SSE state snapshots use an allowlist — internal fields (`notification_recipients`, etc.) are never sent to the browser
- Security response headers on every response (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)

---

## Roadmap

- [ ] PagerDuty / Prometheus webhook trigger (zero-touch incident creation)
- [ ] Slack / Teams notification channel
- [ ] SSO on the approval modal (restrict to authorized SREs)
- [ ] Reject flow re-runs RCA with approver feedback
- [ ] Multi-incident dashboard
- [ ] Real Jira, email, and log integrations

---

## Author

Basit Sherazi
