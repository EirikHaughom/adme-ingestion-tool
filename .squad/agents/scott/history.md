# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Scott owns Azure auth, deployment setup, and environment configuration for the control plane.
- The project will need careful handling of platform credentials, configuration, and operational rollout.
- Issue #8 (user impersonation auth flow) requires explicit Entra app registration prerequisite documentation: redirect URI `http://localhost:8501` must be registered in the Entra app. Missing this URI causes auth to fail at the final browser callback step, even if the MSAL code is correct. This is a configuration issue, not a code issue, and operators must set it up before testing user-impersonation flows.
- Platform prerequisites belong in README.md, not in implementation code. Operator-focused docs catch setup errors early and prevent misattribution to bugs.
- Documentation must stay synchronized with auth UX changes. When user impersonation flow changes from separate-tab-manual-return to browser-automatic-return, README wording describing the UX must be updated to match. Charlie caught this during review—keep docs alive with code.
- Manual token scope feature (post-#8): Token scope is configuration, never credential material. Documentation must clearly distinguish it from secrets and guide operators on when/why to override the default OAuth resource scope. Satya's decision handoff was clear: scope field belongs in Settings, defaults to `https://energy.azure.com/.default`, and requires zero-tolerance messaging against misuse.
- UI-copy alignment is critical for operator safety. Charlie's quality gate caught that Settings TOKEN_SCOPE_HELP lacked explicit "not a token or secret" and "only change when" messaging that the test assertions required. Minimal fix: update the help constant to include all required phrases. No Settings behavior or auth code changes were needed—only copy.

## 2026-05-05: Persistent Storage & Runtime Configuration Plan

**Status:** PLANNING COMPLETE

**Decision:** SQLite is the **default and supported dev storage**. PGlite is documented as **experimental opt-in only**. Production requires PostgreSQL with credentials in Azure Key Vault.

**Key infrastructure decisions:**
- Dev: `./data/adme.db` (SQLite, zero setup), loaded via `python-dotenv` from `.env.local`
- Prod: PostgreSQL 14+ (separate deployment), credentials via Key Vault + `DefaultAzureCredential`
- Alembic manages migrations for both SQLite and PostgreSQL (Kevin owns models, Scott owns infrastructure)
- Environment variables: `ADME_STORAGE_ENGINE`, `ADME_DB_*` for postgres, `ADME_KEYVAULT_ENDPOINT` for Key Vault
- Secrets: Never in plaintext files; `.env` strictly dev-only (documented in README)

**What persists:** ADMEConnection (config), ServiceHealthResult (health runs), soft-deleted via `archived_at` timestamp
**What doesn't:** UserAuthState (session-only), OAuth pending flows (session-only)

**Risks & mitigations:**
- Streamlit Cloud: Force PostgreSQL, warn in README
- Container Instances: PostgreSQL required for HA; SQLite file-locks under concurrency unacceptable
- Azure Web Apps: Ephemeral filesystem; PostgreSQL only
- PGlite confusion: Clear "experimental" label; SQLite is official default

**Scott owns:** Alembic setup, env vars, Key Vault integration, README/runbooks, secrets validation
**Kevin owns:** SQLAlchemy models, database access layer
**Judson owns:** Streamlit session state ↔ database sync (load/save on page lifecycle)

**Operator prerequisites changed:**
- Dev: No new prereqs (SQLite is automatic)
- Prod: PostgreSQL instance (Azure-hosted or external), Key Vault access, network inbound from app region
- Docs: [postgres-setup-guide.md], [migration-guide.md], [secret-rotation.md] TBD in implementation phase

## 2026-05-05: Manual Token Scope Configuration (Complete)

**Status:** COMPLETE
**Decision:** Manual token scope configuration merged to decisions.md
**Outcome:** ADMEConnection now includes token_scope field with ADME default fallback. Settings UI exposes non-secret Token scope field. Both auth paths (user and service principal) consume connection.scope. All validation passed: pytest 80, ruff, mypy.

## 2026-05-05: Persistent Storage & Deployment Configuration Planning (Complete)

**Status:** PLANNING COMPLETE, SYNTHESIZED WITH TEAM

**Decision:** SQLite default for dev; PostgreSQL for production with Azure Key Vault secrets.

**Storage architecture (accepted from plan):**
- **Dev:** SQLite (via SQLAlchemy 2.x + Alembic) at `./data/adme.db` — zero setup, cross-platform
- **Prod:** PostgreSQL 14+ (operator-supplied, separate deployment) via `DATABASE_URL` environment variable
- **Migrations:** Single Alembic tree, runs clean on both SQLite and Postgres
- **Initial scope:** connection_profiles + health_run_summary only; no secrets in database

**Infrastructure owned by Scott (Phase 3):**
1. Alembic setup — config with SQLite + Postgres dialects, auto-generate from Kevin's models
2. Environment variable documentation — DATABASE_URL shape, defaults, validation
3. Key Vault integration — read secrets at startup using `DefaultAzureCredential` (already in auth stack)
4. README & operator runbooks — Postgres setup, migration commands, backup ownership, secret rotation
5. Secrets validation — fail fast if production secrets missing/invalid
6. Local dev setup — ensure `./data/` directory creation, `.gitignore` updates
7. `.env.example` — document all variables; mark `.env` as dev-only (never commit)

**Conflict resolved (Satya/Kevin/Charlie consensus prevails):**
- Scott initially proposed split environment variables: ADME_STORAGE_ENGINE, ADME_DB_HOST, ADME_DB_PORT, ADME_DB_NAME, ADME_DB_USER, ADME_DB_PASSWORD
- Scott initially proposed persisting client_secret in database
- **Decision:** Single DATABASE_URL contract (no split variables). Kevin's repository boundary forbids all secret persistence. Scott to reconcile Key Vault integration to resolve into DATABASE_URL before passing to storage layer (future decision if needed).

**Deployment risks & mitigations documented:**
- Streamlit Cloud: Ephemeral filesystem → force PostgreSQL (warn in README)
- Azure Container Instances: SQLite file-locks under multi-instance scaling → PostgreSQL required
- Azure Web Apps: Ephemeral filesystem → PostgreSQL required
- PGlite confusion: Mark as "experimental"; SQLite is official default

**Operator prerequisites (new):**
- **Dev:** No change (SQLite is automatic)
- **Prod:** PostgreSQL 14+ instance, Key Vault access, network inbound from app region

**Next steps:**
1. Team sign-off on backend contract (especially DATABASE_URL vs split variables)
2. Kevin builds Phase 1 storage foundation (models, repositories, tests)
3. Scott sets up Alembic infrastructure and reconciles Key Vault plumbing to DATABASE_URL
4. Judson wires Phase 2 UI persistence (Settings/Welcome load/save)
5. Charlie gates all phases with comprehensive test suite (A1–A8 acceptance criteria)

**Ownership summary:**
- Kevin: SQLAlchemy models, repository layer, database access
- Judson: Streamlit session state ↔ database synchronization
- Scott: Alembic setup, env vars, Key Vault plumbing, operator docs
- Charlie: Acceptance criteria verification, test matrix (SQLite + Postgres)

## 2026-05-05: Persistent Storage Operator Documentation (Complete)

**Status:** COMPLETE

**Decision:** Added comprehensive **Data Storage** section to README.md documenting the accepted persistent storage contract for operators.

**Key documentation additions:**
- **Development:** SQLite default at `.adme/adme.db`, auto-migrations on startup, zero setup required
- **Production/shared:** PostgreSQL 14+ via `DATABASE_URL` environment variable (single contract, no split variables)
- **Migrations:** Auto for SQLite dev; explicit `alembic upgrade head` for PostgreSQL production before app startup
- **Credentials:** Azure Key Vault or environment secrets only; never plaintext config files
- **What persists:** Connection profiles and health check results (non-sensitive)
- **What doesn't:** Client secrets, access tokens, authorization codes, user auth material (session-only)
- **Limitations:** SQLite not supported for Streamlit Cloud, Azure Web Apps, or multi-instance deployments (PostgreSQL required)
- **Stack update:** Added `Storage: SQLAlchemy 2.x, Alembic` to technology table

**Operator-facing clarity:**
- Single `DATABASE_URL` contract prevents environment variable confusion
- Explicit migration commands protect production deployments from accidental data loss
- Non-secret/secret boundary clearly stated for credential handling
- Deployment constraints documented upfront (SQLite limitations on Streamlit Cloud, containers, HA)

**Decision file:** `.squad/decisions/inbox/scott-storage-docs.md`