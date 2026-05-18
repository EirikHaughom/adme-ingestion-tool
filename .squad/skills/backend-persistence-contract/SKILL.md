---
name: backend-persistence-contract
description: Plan persistent storage in this Python Streamlit app without leaking auth/session secrets
domain: backend, persistence, sqlalchemy, streamlit
confidence: high
source: earned (persistent storage planning)
---

## Context

Use this skill when adding durable storage to the ADME Streamlit control plane. The current app separates static ADME connection configuration, session-scoped user auth material, and health validation results. Persistence must preserve that separation.

## Patterns

- Use a single SQLAlchemy-backed storage boundary under `app\storage\`; app and UI code should call repositories, not ORM rows or raw sessions.
- Default local development to SQLite through `DATABASE_URL` fallback; use a separate PostgreSQL instance only when the operator provides a PostgreSQL database URL.
- Do not use PGlite inside this Python backend unless the project accepts a separate JavaScript sidecar and its failure modes.
- Persist non-secret connection profiles and health-check summaries/results first.
- Never persist `client_secret`, MSAL pending flows, authorization codes, access tokens, refresh tokens, or token caches.
- Keep `ADMEConnection` as static configuration and `UserAuthState` as Streamlit-session auth material.
- Run SQLite migrations automatically only for local dev; require explicit Alembic migration operations for PostgreSQL deployments.
- Keep SQLAlchemy sessions transaction-scoped and outside Streamlit session state.
- Redact database URLs in logs and operator messages.

## Examples

- `app\models\connection.py` defines the static connection dataclass that storage should map to and from.
- `app\connection_state.py` owns Streamlit session keys and should remain separate from durable persistence.
- `app\services\auth.py` keeps `UserAuthState` and pending MSAL flow material out of persistent models.
- `.squad\decisions\inbox\kevin-storage-contract.md` records the first backend persistence plan.

## Anti-Patterns

- Persisting service-principal client secrets in the profile table.
- Falling back from broken production PostgreSQL to SQLite, which silently forks operator state.
- Splitting database config into many environment variables before the backend has one redaction and precedence contract.
- Letting Streamlit pages import SQLAlchemy models directly.
- Hiding SQLite lock or PostgreSQL outage behind unbounded retries.
- Adding PostgreSQL-specific column types before the SQLite/PostgreSQL portability contract is intentionally broken.
