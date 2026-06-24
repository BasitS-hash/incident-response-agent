# Contributing

Thanks for your interest in improving the Incident Response Agent. This guide covers the
local setup and the standards your change should meet before opening a pull request.

## Development Setup

```bash
# Backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# Frontend
cd frontend && npm install && cd ..
```

Copy `.env.example` to `.env` and fill in at least a `GEMINI_API_KEY` (or set
`LLM_PROVIDER=openai` with an `OPENAI_API_KEY`). Tests do not require any keys.

## Project Layout

- `backend/agents/` — the five incident-response agents (intake, triage, RCA, notify).
- `backend/graph/` — LangGraph state machine, routing, and state schema.
- `backend/mcp_server/tools/` — data-source adapters (Jira, logs/metrics, email).
- `backend/api/main.py` — FastAPI app: auth, validation, rate limiting, SSE.
- `tests/` — pytest suite; external calls are mocked via `tests/conftest.py`.

## Before You Open a PR

Run the same checks CI runs and make sure they all pass:

```bash
ruff check backend tests                              # lint (must pass)
mypy backend                                          # type-check
bandit -r backend -ll                                 # SAST (must pass)
pip-audit -r backend/requirements.txt                 # dependency CVEs
pytest tests --cov=backend --cov-report=term-missing  # tests + coverage
```

Requirements:

- **Lint clean** — `ruff check` must report no errors.
- **Tests pass** — all tests green.
- **Coverage ≥ 80%** — CI enforces `--cov-fail-under=80`. New logic needs new tests.
- **No secrets** — never commit credentials. Use environment variables.
- **No `eval` / `exec` / `shell=True`** — and validate any new external input at the boundary.

## Coding Standards

- Python: PEP 8, type hints on function signatures, small focused functions, parameterized SQL.
- Keep the LLM lazy — fetch it via `get_cached_llm()` inside functions, never at module import time
  (importing the package must not require an API key).
- Add tests alongside any new agent logic, tool, or endpoint. Mock the LLM with the `fake_llm_factory`
  fixture and mock external services with `monkeypatch`.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Slack notification channel
fix: handle empty affected_systems in RCA agent
test: cover triage memory truncation
docs: expand architecture diagram
chore: pin transitive dependency
```

## Reporting Security Issues

Do **not** open a public issue for vulnerabilities — follow [`SECURITY.md`](./SECURITY.md).
