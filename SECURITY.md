# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public issue.**
Instead, report it privately:

1. Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
   ("Report a vulnerability" under the **Security** tab), **or**
2. Email the maintainer directly.

Please include: a description, reproduction steps, affected version/commit, and impact.
You can expect an acknowledgement within **5 business days** and a remediation plan
for confirmed issues.

## Supported Versions

This is a portfolio / reference project. Security fixes are applied to the `main` branch only.

## Security Design

The application is built defensively. Key controls:

| Area | Control |
|------|---------|
| **Authentication** | `X-API-Key` header required on all state-changing and audit endpoints. `API_KEYS` maps each key to a named principal and a scope set (`submit` / `approve`). With neither `API_KEY` nor `API_KEYS` set, an explicit dev mode is enabled and logged as a warning at startup. |
| **Approver identity** | `POST /approve` records the principal bound to the presented key, never an `approver` from the request body; a body that disagrees with its credential is refused, and the legacy unnamed `API_KEY` cannot approve. This is attribution to a key holder, not authentication of a person — a leaked key is an impersonation. See the "On who approved" note in [`README.md`](./README.md#security). |
| **Rate limiting** | `slowapi` per-IP limits: 10/min on `POST /incident`, 20/min on `POST /approve`, 30/min on search. |
| **Input validation** | Pydantic models validate every request body. Incident IDs must match `^[A-Z]+-\d+$`; principal names configured in `API_KEYS` are length- and charset-restricted to the audit column's shape; notes have control characters stripped. |
| **Prompt-injection hardening** | Mem0 memory injected into prompts is truncated (500 chars/entry) to limit RAG poisoning blast radius. Approval notes are sanitized before storage. |
| **Output minimization** | A response allowlist (`_safe_state`) strips internal fields (LLM `messages`, `notification_recipients`, raw `similar_incidents`) so they never reach the browser. |
| **Parameterized SQL** | The SQLite audit log uses parameterized queries exclusively — no string interpolation. |
| **Audit tamper evidence** | Every audit write appends a hash-chained entry over a canonical snapshot of the run row. `python -m backend.audit.verify` (or `GET /audit/verify`) names the first entry that does not hold up. This is evidence, not immutability: it catches edits made without recomputing the chain, not a full rewrite of `audit.db` — see the audit-chain note in [`README.md`](./README.md#security). |
| **No `eval` / shell** | No use of `eval`, `exec`, `os.system`, or `shell=True` anywhere in the codebase. |
| **Security headers** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` on every response. |
| **CORS** | Explicit localhost origin allowlist; no wildcard origin combined with credentials. |
| **Transport** | Warns if `LANGFUSE_HOST` sends LLM traces to a remote host over plain HTTP. |
| **Startup validation** | `validate_config()` fails fast on a missing/invalid LLM provider key. |

## Secret Management

- **No secrets are committed to the repository.** All credentials are read from environment
  variables (or a local `.env` file, which is git-ignored). See `.env.example` for the schema.
- The `docker-compose.yml` observability stack ships with **intentionally weak placeholder**
  values (`NEXTAUTH_SECRET`, `SALT`, `POSTGRES_PASSWORD`) clearly marked **local-dev-only**.
  Rotate these before any non-local deployment.
- If you ever expose this service publicly, **set `API_KEYS`** (long random keys, one principal
  per key) and rotate any credentials that may have been logged. Key material is never written to
  a log line or returned in a response, including in configuration-error messages.

## Automated Security Scanning

Every push and pull request runs:

- **Bandit** — Python static application security testing (SAST)
- **pip-audit** — dependency CVE auditing against pinned `requirements.txt`
- **gitleaks** — secret scanning across the full git history
- **Trivy** — container image and filesystem vulnerability scanning (results to the GitHub Security tab)
- **CodeQL** — semantic code analysis (`security-extended`) for Python and TypeScript

Dependabot opens weekly update PRs for pip, npm, Docker, and GitHub Actions dependencies.
