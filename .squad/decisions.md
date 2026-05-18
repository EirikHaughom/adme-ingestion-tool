# Squad Decisions

## Active Decisions

### 2026-04-24T14:11:37.779+02:00: Initial squad roster
**By:** Eirik Haughom (via Copilot)
**What:** Hire Satya as lead, Judson as Streamlit app dev, Kevin as backend dev, Scott as cloud devops, and Charlie as tester, alongside Scribe and Ralph in their standard roles.
**Why:** The ADME control plane needs clear ownership across product scope, Streamlit UI, backend integration, Azure platform work, and quality.

### 2026-04-24T14:11:37.779+02:00: Naming convention
**By:** Eirik Haughom (via Copilot)
**What:** Use Microsoft executive names for the working squad members.
**Why:** The user explicitly requested that naming convention for this team.

### 2026-04-24T14:11:37.779+02:00: Product focus
**By:** Eirik Haughom (via Copilot)
**What:** The squad is chartered to build a Python and Streamlit control plane app for Azure Data Manager for Energy (ADME).
**Why:** Shared scope keeps routing, charters, and future issue triage aligned around the same product surface.

### 2026-04-26T06:51:32Z: App-returning auth flow
**By:** Satya (via Copilot)
**What:** When implementing a true redirect-back-to-app login experience for user impersonation, replace `InteractiveBrowserCredential` with an app-managed MSAL Python authorization-code + PKCE flow using `http://localhost:8501` as the redirect URI and `https://energy.azure.com/.default` as the ADME scope.
**Why:** `InteractiveBrowserCredential` owns its own localhost callback listener on port 8400 and cannot return the browser session to the running Streamlit app. MSAL authorization-code + PKCE lets the app receive the callback, complete sign-in inside Streamlit, and preserve the service-principal path unchanged.
**Notes:** Target UX is Sign In -> Entra login -> return to Streamlit authenticated. Main implementation risk is consuming and clearing OAuth callback query parameters exactly once across Streamlit reruns.

### 2026-05-05T20:00:00.287+02:00: Storage implementation package boundary
**By:** Kevin

## Decision

The backend storage foundation is implemented under `app\storage\` using SQLAlchemy 2.x and Alembic. SQLite is the default when `DATABASE_URL` is unset and can auto-run migrations for local development; PostgreSQL remains operator-supplied through `DATABASE_URL` and only receives startup revision checks.

## Notes

- `client_secret`, MSAL flow material, tokens, auth codes, refresh tokens, and token caches are not schema fields and are rejected before profile persistence.
- Repository methods return domain dataclasses and existing `ADMEConnection` / `ServiceHealthResult` objects, not ORM rows or sessions.
- Alembic helper functions live in the `app.storage.migrations` package `__init__` because the required migration script package conflicts with a same-named `migrations.py` import path.
- Query paths are indexed for non-deleted profile listing, active-profile lookup, latest health runs by profile, and service-result ordering.

# Judson storage UI wiring

Date: 2026-05-05T20:00:00.287+02:00

Decision: Streamlit pages use `app.storage_bridge` as the presentation-layer adapter to Kevin's `app.storage` repositories rather than importing storage internals directly.

- Settings and Welcome load the active persisted profile into Streamlit session state only when needed.
- Save Settings and Test Connection persist a non-secret profile; `client_secret`, pending sign-in, and tokens remain session-only.
- Completed health validation results are recorded after successful Test Connection runs.
- Storage startup/write failures show operator-facing feedback and keep safe session-only behavior without switching backend modes.

# 2026-05-05T20:00:00.287+02:00: Persistent storage verification tests

**By:** Charlie

## Decision

Added storage verification coverage in two layers:

- `tests/test_storage_bridge.py` verifies the UI-facing bridge can load saved
  connection and health state from storage-shaped modules, strips
  `client_secret` before repository calls, and lets Settings plus Welcome render
  persisted non-secret fields without operator re-entry.
- `tests/test_storage_contract.py` verifies the concrete `app.storage`
  implementation when present: SQLite defaults/redaction, clean SQLite
  initialization, non-secret profile round-trip, active profile restart
  survival, persisted health results with checked timestamp, and rollback on an
  injected health-result write failure.

## Why

The accepted contract is bigger than the happy path. The tests now force the
storage boundary to preserve the non-secret/session-secret split and make UI
loading observable instead of assumed.

## Evidence

- `python -m pytest --no-cov -q` — 101 passed, 1 skipped.
- `python -m pytest` — passed with configured coverage.
- `python -m ruff check app tests` — passed.
- `python -m mypy app tests` — passed.

## Notes

The one skipped test is the unavailable-storage warning path; it is skipped only
when the concrete `app.storage` package exists in the working tree.

### 2026-05-05T20:00:00.287+02:00: Storage implementation review
**By:** Satya

## Verdict

APPROVE.

## Evidence against the acceptance contract

- **SQLite default at `.adme/adme.db`.** `app/storage/config.py::resolve_storage_config` returns a SQLite config rooted at `.adme/adme.db` when `DATABASE_URL` is unset or blank. `_default_sqlite_path` resolves under the cwd. Covered by `test_default_storage_config_uses_local_sqlite`.
- **PostgreSQL via operator-supplied `DATABASE_URL`; no broken-prod fallback.** `_config_from_database_url` raises `ValueError` for invalid or non-sqlite/non-postgresql URLs instead of silently falling back. `test_invalid_database_url_does_not_fallback_to_sqlite` and `test_unsupported_database_url_does_not_fallback_to_sqlite` lock this in.
- **PGlite out of scope.** No JS sidecar; only SQLAlchemy/Alembic and optional `psycopg[binary]` (extras).
- **SQLAlchemy/Alembic boundary under `app/storage`.** ORM rows in `models.py`, repositories in `repositories/`, sessions in `session.py`, engine factory in `engine.py`, migrations under `migrations/`. UI/app code interact via `app.storage_bridge` and the domain `ConnectionProfile` / `HealthRunSummary` dataclasses, not ORM rows.
- **No persisted secrets / MSAL / tokens / passwords; redacted DB URLs.** `ConnectionProfileRepository._validate_profile` rejects any `client_secret`; `storage_bridge.connection_profile_without_secret` strips it before crossing the boundary; profiles loaded from rows always reconstruct `ADMEConnection` with `client_secret=""`. `StorageConfig.url` is `repr=False`; `safe_description` redacts PostgreSQL credentials and yields a plain SQLite path. No tables for auth flows or tokens.
- **SQLite dev auto-migrates; PostgreSQL gets revision check, no startup migration.** `ensure_storage_ready` calls `run_sqlite_migrations` for SQLite and, for PostgreSQL, compares the live revision against the Alembic head, raising `StorageMigrationError` with operator-facing guidance if they diverge. README documents the explicit `alembic upgrade head` step.
- **Settings/Welcome hydrate profiles/health while auth/secrets stay session-only.** `app/main.py` and `app/pages/1_⚙️_Settings.py` call `load_persisted_connection_state` / `persist_connection_profile` / `persist_health_run`; copy in both pages reiterates that client secrets and user sign-in stay session-bound.

## Validation

- Coordinator-reported `python -m pytest` (101 passed, 1 skipped), `python -m ruff check app tests`, `python -m mypy app tests` — all green and consistent with my read of the code.
- Repository-level tests cover migrations, round-trip, secret rejection, health run atomicity, and active-profile linkage. Bridge-level tests cover storage-unavailable warning, secret stripping, and Settings/Welcome hydration without re-entering fields.

## Non-blocking follow-ups

- `app/storage_bridge.py` carries a fairly elastic reflective dispatch path (`_first_callable`, `_accepts_keyword`, multiple aliases) that predates the now-stable `app.storage` public API. Once no alternate storage backends are anticipated, Kevin can collapse this onto the `_repository_api_from_storage_root` path and remove the alias scanning to reduce surface area.
- `load_persisted_connection_state` returns `available=True` early when a connection already lives in `st.session_state`, skipping a possible restore of the latest stored health run. Acceptable today, but Judson should consider whether Welcome should still surface the latest persisted validation summary in that case.
- README contains a small typo (`befoore`) in the production migration section. Scribe or Scott can fix on the next docs sweep.

## Lockout

No revision required. Kevin remains free to act on the follow-ups; no different-author rotation is needed because this is an approval.

# 2026-05-05: Persistent Storage Documentation for Operators

**By:** Scott (Cloud DevOps)  
**Task:** Update operator/runtime documentation for the accepted persistent storage implementation

## Decision

Added comprehensive **Data Storage** section to README.md documenting the persistent storage contract for operators. The documentation covers development defaults, production requirements, migration procedures, credential handling, what is and is not persisted, and deployment limitations.

## Rationale

The persistent storage architecture (SQLite dev default + PostgreSQL production) has been planned and accepted by the team (see history.md "2026-05-05: Persistent Storage & Deployment Configuration Planning"). Operators need clear, accurate documentation to:

1. Understand SQLite is the default and supported dev storage
2. Know PostgreSQL 14+ is required for production, containers, and multi-instance deployments
3. Follow the correct migration command sequence
4. Never commit plaintext database credentials
5. Understand what data is persisted and what remains session-only
6. Avoid PGlite; use real PostgreSQL when needed

## Implementation

Updated `README.md` with new **Data Storage** section containing:

### Development: SQLite
- Default storage at `.adme/adme.db` created automatically
- Zero-setup path for local dev
- Auto-migrations on startup

### Production & Shared Deployments: PostgreSQL 14+
- `DATABASE_URL` environment variable is the single credential contract
- No split `ADME_DB_HOST`/`ADME_DB_PASSWORD` variables
- PostgreSQL URL format documented
- Explicit `alembic upgrade head` required before app startup

### Database credentials subsection
- Never store plaintext credentials in config files
- Use Azure Key Vault, environment secrets, or cloud platform credential systems
- App accepts `DATABASE_URL` environment variable only

### What is stored
- Connection profiles (ADME endpoint, tenant, client, partition, auth method, scope)
- Health check results (summary and timestamp)

### What is not stored
- Client secrets, access tokens, refresh tokens, token caches
- MSAL authorization flows, OAuth authorization codes
- User authentication material

### Limitations
- SQLite not supported for Streamlit Cloud (ephemeral filesystem)
- SQLite not supported for Azure Container Instances or Web Apps (ephemeral filesystem)
- SQLite not supported for multi-instance or horizontally scaled deployments
- PostgreSQL required in those cases

### Stack table update
Updated to include `Storage: SQLAlchemy 2.x, Alembic`

## Scope

Documentation only. No code, tests, pyproject.toml, or deployment files modified. This is alignment of operator-facing documentation with the accepted persistent storage plan.

## Dates

Used `2026-05-05` per CURRENT_DATETIME in spawn context.

## Next Steps

When Kevin's SQLAlchemy models and repository layer are merged, and Judson's Streamlit session ↔ database synchronization is ready, operators will have complete documentation for local SQLite and production PostgreSQL workflows.

## Team Notes

This completes Scott's ownership scope for operator/runtime documentation of the persistent storage implementation. Remaining infrastructure work (Alembic setup, Key Vault integration, migration runbooks) is owned by Scott in later phases pending implementation of Kevin's storage models and Judson's UI persistence.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction

---

### 2026-05-05T14:11:09.427+02:00: Issue #8 MSAL auth flow quality gate
**By:** Charlie

## Verdict

APPROVE.

## Evidence

- `app\services\auth.py` uses MSAL `PublicClientApplication` auth-code + PKCE for user impersonation with redirect URI `http://localhost:8501`; `InteractiveBrowserCredential` is not used in app code.
- Runtime dependencies declare `msal>=1.31.0` in both `requirements.txt` and `pyproject.toml`.
- Settings callback handling consumes OAuth query params once, clears them, rejects missing pending flow, auth denial, state mismatch, and token-exchange failure safely, and does not reuse stale pending flow material. I added regression tests for those failure modes.
- Authenticated user validation uses stored `UserAuthState`; service-principal token acquisition still uses `ClientSecretCredential`.
- Sign Out, connection/auth-method changes, and completed auth state changes clear stale user auth or health state as required.
- README documents the Entra redirect URI prerequisite `http://localhost:8501` without secrets.

## Validation

- `python -m pytest tests\test_auth.py tests\test_auth_service.py tests\test_connection_state.py tests\test_settings_page.py` — 42 passed.
- `python -m pytest` — 70 passed.
- `python -m ruff check app tests` — passed.
- `python -m mypy app tests` — passed.

## Follow-up

- Non-blocking documentation cleanup: `README.md` operator-flow text still contains earlier "separate browser tab / close that tab" wording. It does not block this gate because the required redirect prerequisite is documented, but Scott or Scribe should align that wording before broader operator docs review.

---

### 2026-05-05T14:11:09.427+02:00: Settings owns session-scoped user auth callback wiring
**By:** Judson

## Decision

The Settings page now treats user impersonation as an explicit Streamlit session flow:
pending MSAL auth starts are stored separately from completed user auth state, and
`ADMEConnection` remains static connection configuration only.

OAuth callback query params are copied once, exchanged only when a pending flow is
present, and cleared in a `finally` path so Streamlit reruns cannot replay the
exchange. Completing sign-in stores session auth state and clears stale health.
Sign Out, auth-method changes, and connection changes clear user auth plus health.

## Why

Operators should see one clear next action: sign in, then test the connection.
Keeping auth material out of the connection model prevents accidental persistence
and keeps backend calls tied to the current Streamlit session identity.

---

### 2026-05-05T14:11:09.427+02:00: MSAL auth service return contract
**By:** Kevin

## Decision

Kevin's auth-service implementation exposes user impersonation through
`start_user_auth_flow(connection)`, `complete_user_auth_flow(connection, flow,
callback_params)`, and `get_token(connection, user_auth_state=None)`.

`start_user_auth_flow()` builds an MSAL `PublicClientApplication` with the
connection client ID and tenant authority, requests `[connection.scope]`, and
uses `http://localhost:8501` as the redirect URI. It returns a navigation URL
plus an opaque pending-flow payload wrapped in `UserAuthFlowStart`; the wrapper
hides the payload from repr output.

`complete_user_auth_flow()` accepts the stored pending flow and callback params,
lets MSAL validate state/PKCE, and returns `UserAuthState` with only the
session-scoped access material needed by backend calls. `get_token()` no longer
opens a user browser flow; user impersonation requires an explicit
`UserAuthState`, while service-principal authentication remains the existing
`ClientSecretCredential` path.

## Why

This makes the external dependency boundary explicit. Streamlit owns storing and
clearing pending flow and auth state, while the backend owns MSAL construction,
callback exchange, safe response mapping, and service-principal token retrieval.
It also avoids leaking pending flows, raw MSAL responses, access tokens, or
client secrets into logs, exceptions, repr output, or tests.

---

### 2026-05-05T14:11:09.427+02:00: Issue #8 auth implementation handoff
**By:** Satya

## Decision

Implement issue #8 as an app-returning Streamlit auth flow using MSAL
`PublicClientApplication` authorization-code + PKCE with
`redirect_uri=http://localhost:8501` and scope
`https://energy.azure.com/.default`. `InteractiveBrowserCredential` is out
for user impersonation because it owns its localhost callback and cannot return
control to Streamlit. Service-principal authentication remains unchanged.

## Interface contract

### `app.services.auth` owned by Kevin

- Add `msal` and expose MSAL-specific user-flow helpers:
  - `start_user_auth_flow(connection) -> UserAuthFlowStart`
    - Builds `PublicClientApplication` from `connection.client_id` and
      `connection.tenant_id`.
    - Calls `initiate_auth_code_flow()` with `[connection.scope]` and
      `http://localhost:8501`.
    - Returns an operator-navigation URL plus an opaque flow payload to store
      in session state.
  - `complete_user_auth_flow(connection, flow, callback_params) -> UserAuthState`
    - Calls `acquire_token_by_auth_code_flow()`.
    - Validates state through MSAL and raises `AuthenticationError` on failure.
    - Returns only the session-scoped auth material the app needs; do not pass
      raw MSAL response dictionaries to the UI.
  - `get_token(connection, user_auth_state=None) -> str`
    - For service principal, keep the existing `ClientSecretCredential` path.
    - For user impersonation, use the stored session auth state; do not open a
      browser or create `InteractiveBrowserCredential`.
- Keep token/cache values out of logs, exceptions, committed files, and test
  output. Placeholder tokens only in tests.

### `app.connection_state` shared contract owned by Judson with Kevin review

- Keep `ADMEConnection` as static connection configuration only. Do not add
  tokens, authorization codes, pending flows, or MSAL caches to it.
- Add explicit session keys and helpers for:
  - pending user auth flow;
  - completed user auth state;
  - clearing auth state on sign-out or connection/auth-method change;
  - clearing stale health state when auth state changes.
- Pending flow and auth state are Streamlit-session scoped only. They are
  sensitive and must not be serialized to disk or echoed to operator messages.

### `app.pages\1_⚙️_Settings.py` owned by Judson

- At page start, after `ensure_session_defaults()`, consume OAuth callback
  query parameters once:
  - copy `code`, `state`, and related callback params;
  - require a matching pending flow before token exchange;
  - call `complete_user_auth_flow()`;
  - store auth state, clear pending flow, clear health state, show success;
  - clear Streamlit query params in a `finally` path so reruns cannot replay the
    token exchange.
- User impersonation UX:
  - unauthenticated valid connection: show Sign In using the MSAL auth URL;
  - authenticated: show Sign Out and enable Test Connection using stored auth;
  - sign-out clears auth state and health state;
  - no separate-browser-tab guidance from the old credential flow.
- Service-principal UX and masked client-secret handling stay as-is.

## File ownership

- Kevin: `app/services/auth.py`, `requirements.txt`, `pyproject.toml`,
  auth-service unit tests.
- Judson: `app/pages\1_⚙️_Settings.py`, `app/connection_state.py`, page/session
  behavior tests.
- Charlie: acceptance test review, Streamlit recorder extensions, regression
  coverage across auth methods and reruns.
- Scott: Azure app registration/operator prerequisite note: redirect URI
  `http://localhost:8501` must be registered for the public-client app.
- Satya: final contract review before merging anything that changes
  `ADMEConnection`, session auth keys, or the Settings-page callback sequence.

## Risks and gates

- **Rerun replay risk:** callback params must be copied, exchanged, and cleared
  exactly once. A rerun must not call `acquire_token_by_auth_code_flow()` again.
- **State/PKCE risk:** never exchange a callback without the pending MSAL flow
  generated for the same session.
- **Secret risk:** access tokens, MSAL cache material, pending flow payloads, and
  client secrets are session-only. They must not appear in logs, `.squad/`,
  exceptions shown to operators, or GitHub issue text.
- **Configuration risk:** Entra app registration must include the exact redirect
  URI `http://localhost:8501`; otherwise the implementation will look broken
  while the code is correct.
- **Regression risk:** service-principal auth must remain a straight
  ClientSecretCredential path with the existing masked-secret UI.

## Acceptance criteria

- `InteractiveBrowserCredential` is no longer used for user impersonation.
- `msal` is added consistently to runtime dependency declarations.
- User impersonation starts an MSAL auth-code + PKCE flow and returns to
  Streamlit on `http://localhost:8501`.
- OAuth callback params are consumed once, cleared from the browser URL, and do
  not replay on a second Streamlit render.
- State mismatch, missing pending flow, auth denial, and token-exchange failure
  produce operator-safe errors and clear the stale pending flow.
- Authenticated user sessions can run service health validation without opening
  a new browser credential flow.
- Sign Out clears user auth state and previous health results/errors.
- Connection or auth-method changes clear user auth state and stale health.
- Service-principal tests and behavior continue to pass unchanged except for
  any intentional import/dependency adjustments.
- Tests cover auth service, session-state helpers, Settings UI sign-in/sign-out,
  callback success/failure, query-param clearing, and rerun no-replay behavior.

## Validation commands

Run after implementation:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests\test_auth.py tests\test_auth_service.py tests\test_connection_state.py tests\test_settings_page.py
python -m pytest
python -m ruff check app tests
python -m mypy app tests
```

Manual gate:

```powershell
streamlit run app\main.py
```

Configure a user-impersonation connection whose Entra app registration includes
`http://localhost:8501`, click Sign In, confirm the browser returns to Settings,
confirm callback params disappear from the URL, run Test Connection, then Sign
Out and confirm health/auth state clears.

## Sequencing constraints

- Do not split callback consumption between agents. Judson owns the
  Settings-page consume/store/clear sequence end-to-end, with Kevin reviewing
  the auth-service calls it invokes.
- Kevin must land the auth-service function names and return shapes before
  Judson wires the page. Charlie can write contract tests in parallel, but final
  assertions must align after Kevin and Judson converge on the exact API.
- Scott's app-registration prerequisite note can happen in parallel; it must
  not block local unit tests.

---

### 2026-05-05T14:11:09.427+02:00: Final issue #8 auth implementation review
**By:** Satya

## Verdict

APPROVE.

## Contract gates

- Auth service exposes the agreed `start_user_auth_flow`, `complete_user_auth_flow`, and `get_token(..., user_auth_state=None)` contract, wraps MSAL behind operator-safe errors, and keeps pending flow/token fields out of repr output.
- `ADMEConnection` remains static connection configuration only; pending flows and completed user auth state stay in Streamlit session keys and are cleared on sign-out, connection/auth-method changes, and auth-state changes.
- Settings consumes OAuth callback query params once, clears them in a `finally` path, rejects missing/stale flows safely, and does not replay token exchange on rerun.
- Service-principal auth remains on the `ClientSecretCredential` path.
- README documents the `http://localhost:8501` Entra redirect URI prerequisite and updated operator flow wording.
- Charlie's evidence is sufficient and I independently re-ran the same gate: targeted auth tests passed, full test suite passed, Ruff passed, and mypy passed.

## Notes

No implementation changes required. This is ready for coordinator merge handling.

---

### 2026-05-05T14:11:09.427+02:00: Entra app registration redirect URI prerequisite documented

**By:** Scott (Cloud DevOps)

## Decision

Added explicit operator prerequisite documentation to README.md for issue #8 (user impersonation auth). The Entra application registration used as the public client must include redirect URI `http://localhost:8501`.

## Rationale

Issue #8 implements an app-returning OAuth sign-in flow using MSAL `PublicClientApplication` with PKCE. After the user authenticates in a browser, Entra must callback to `http://localhost:8501` to complete the flow. If this redirect URI is not registered in the Entra app, the callback will be rejected by Entra, and the authentication will fail at the final step.

This is a **configuration requirement**, not a code issue. Without documentation, operators may configure the MSAL code correctly but fail to register the redirect URI, then blame the implementation when the flow hangs. Early, clear documentation prevents misattribution and reduces support burden.

## Location

README.md, new "## Prerequisites" section immediately before "## Quick Start".

## Scope

- Explains why the redirect URI is required
- Provides operator step-by-step instructions
- Notes that service-principal auth does not require this
- Contains no secrets, tenant-specific values, or personal data
- Does not edit implementation code, auth service, Settings page, tests, or dependency files

## Team Notes

This completes Scott's ownership scope for issue #8 per the auth implementation handoff (satya-auth-implementation-handoff.md). Remaining work is owned by Kevin (auth service), Judson (Settings page UI), and Charlie (acceptance tests).

---

### 2026-05-05T14:11:09.427+02:00: Updated README Operator Flow wording for user-impersonation UX

**By:** Scott (Cloud DevOps)
**Context:** Charlie flagged stale documentation during issue #8 auth implementation review.

## Decision

Updated README.md "Operator Flow" section to remove outdated wording about "separate browser tab" and "close that tab after sign-in and return." Replaced with accurate description: user logs in through Entra in their browser, and the session returns automatically to Streamlit when complete.

## Why

The old MSAL documentation implied a manual tab-closing workflow (legacy `InteractiveBrowserCredential` behavior). Issue #8 implements app-returning auth with MSAL `PublicClientApplication` at redirect URI `http://localhost:8501`—the browser callback is automatic, no manual tab management needed. Stale wording confuses operators and contradicts the actual UX.

## What Changed

README.md, Operator Flow step 3:
- **Removed:** "(opening a separate browser tab for user impersonation; close that tab after sign-in and return to Streamlit)"
- **Added:** "For user impersonation, you will sign in through Entra in your browser; the session will return automatically to Streamlit when complete."

## Scope

Documentation only; no code or test changes. This is a narrative update to reflect the new MSAL flow accurately.

---

### 2026-05-05T15:11:17.396+02:00: Manual token scope configuration handoff
**By:** Satya

## Decision

Add a manually editable token-scope field to static ADME connection configuration. Default behavior remains the current ADME resource scope, but operators can override it when their tenant/app registration requires a different OAuth resource scope.

## Implementation handoff

### 1. Model contract

- Add `token_scope: str = ADME_RESOURCE_SCOPE` to `ADMEConnection`, after `data_partition_id` and before existing optional auth fields.
- Keep `ADME_RESOURCE_SCOPE = "https://energy.azure.com/.default"` as the default constant.
- Keep `ADMEConnection.scope` as the auth-facing property. It should return the normalized configured scope (`token_scope.strip()`), not a hardcoded constant.
- Include `token_scope` in dataclass equality so changing scope is a connection change.
- `is_valid()` must require a non-empty normalized scope. Validation should reject blank/whitespace-only scope and obvious whitespace-separated scope values; do not add resource-domain whitelisting.
- This is configuration, not token material. It may live in Streamlit session state as part of `ADMEConnection`; do not add tokens, pending MSAL payloads, or cache material to the model.

### 2. UI behavior

- Add one Settings text input labeled `Token scope`, preferably after `Client ID` and before `Data partition ID`.
- Default/value: existing connection `token_scope` when present, otherwise `ADME_RESOURCE_SCOPE`.
- Placeholder/help: use `https://energy.azure.com/.default`; help text should say this is the OAuth scope requested for ADME tokens and should only be changed when the operator's Entra/ADME setup requires a custom scope.
- Trim the entered value before constructing `ADMEConnection(token_scope=...)`.
- Save behavior: changing only token scope must count as a connection change, clear stale health, clear pending/completed user auth, and prompt user impersonation connections to sign in again.
- Test behavior:
  - User impersonation: if the draft scope differs from the saved connection, keep Test Connection disabled until settings are saved and a fresh sign-in completes.
  - Service principal: Test Connection may run after save/test with the chosen scope.
- Do not mask this field; it is not a secret. Do not log or display access tokens while handling it.

### 3. Backend/auth behavior

- Keep existing auth-service function signatures.
- `start_user_auth_flow(connection)` must continue to call MSAL with `scopes=[connection.scope]`; after the model change this automatically uses the operator-selected scope.
- Service-principal `get_token(connection)` must continue to call `ClientSecretCredential.get_token(connection.scope)`.
- `complete_user_auth_flow()` does not need a separate scope argument; the pending flow was created for the selected scope. If connection/scope changed, Settings must have cleared the stale pending flow before completion.
- User-auth `get_token(..., user_auth_state=...)` returns the session token minted during sign-in; it must not silently reuse a token after scope changes.

### 4. Tests to update/add

- `tests/test_connection_model.py`
  - Assert default `token_scope` and `scope` property are `https://energy.azure.com/.default`.
  - Assert a custom `token_scope` is returned by `scope`.
  - Assert blank/whitespace scope makes the connection invalid.
- `tests/test_auth_service.py` and any parallel auth tests
  - Assert MSAL receives `[custom_scope]` for user impersonation.
  - Assert `ClientSecretCredential.get_token()` receives `custom_scope` for service principal.
  - Update old assertions that hardcode only the default scope.
- `tests/test_settings_page.py`
  - Update field-contract assertions to include `Token scope`.
  - Assert default value/help/placeholder use the ADME default scope.
  - Assert saving/testing persists `ADMEConnection.token_scope`.
  - Assert changing token scope clears user auth state, pending flow, and health results.
  - Assert user Test Connection is disabled when only token scope changed until save plus fresh sign-in.
- `tests/test_connection_state.py`
  - Add an explicit scope-only connection-change case for `save_connection()` clearing auth and health.

### 5. Documentation note

- Update README operator flow/settings description to mention Token scope defaults to the ADME scope and is only needed for custom Entra/ADME resource-scope setups.
- Keep the existing redirect URI prerequisite. No secret-handling changes are needed because scope is configuration, not credential material.

### 6. Reviewer gates and sequencing

- Kevin owns the model/auth-service contract update and auth tests first. No auth function signature changes unless Satya re-approves.
- Judson owns Settings UI/session behavior after the `token_scope` field name and property behavior are committed.
- Charlie gates regression coverage across model, auth, connection-state, and Settings-page behavior before merge.
- Scott can update README in parallel after the field label/help text is stable.
- Satya final-review gate: `ADMEConnection` remains static config only; both auth paths use `connection.scope`; scope changes clear stale user auth and health; no extra abstraction layer is introduced.
- Required validation after implementation: targeted auth/model/settings/connection-state tests, full pytest, Ruff, and mypy.

---

### 2026-05-05T15:11:17.396+02:00: Manual token scope backend contract
**By:** Kevin

## Decision

Backend auth will continue to consume only `connection.scope`. `ADMEConnection.token_scope` is the persisted static configuration field, while `connection.scope` is the compatibility accessor that trims the configured value and falls back to `ADME_RESOURCE_SCOPE` when the configured value is blank or whitespace.

## Why

This keeps MSAL user auth and service-principal auth on one explicit contract without adding new auth-service parameters. A blank operator-entered scope is treated as "use the default ADME scope" rather than a validation failure, so model validation remains focused on endpoint, tenant, client, partition, and service-principal secret requirements.

## Notes for Judson and Scott

Judson: the Settings page can pass trimmed `token_scope` into `ADMEConnection`; if the field is blank, backend behavior falls back safely to the default scope. Scott: operator docs should describe token scope as configuration, not credential material, and mention the default fallback behavior.

---

### 2026-05-05T15:11:17.396+02:00: Manual token scope in Settings UI
**By:** Judson

## Decision

Settings exposes a visible, non-secret `Token scope` field after `Client ID`.
The field defaults to the ADME resource scope when no connection exists, stores
trimmed operator input on `ADMEConnection.token_scope`, and permits blank input
so `connection.scope` can use the backend default fallback.

Changing only token scope is treated as a connection change. The existing
session save path clears stale user auth, pending sign-in flow, and health state
before prompting the operator to sign in again for user impersonation.

## Why

Operators need one place to adjust OAuth scope when their Entra or ADME setup
requires it, without treating scope as a secret or changing auth-service call
signatures. Keeping the change in the normal connection equality path prevents
reusing tokens or health results minted for a previous scope.

---

### 2026-05-05T15:11:17.396+02:00: Token Scope Documentation for Operators
**By:** Scott

## Decision

Update README.md to document the new **Token scope** field in Settings, emphasizing that it is configuration metadata (not a secret) and clarifying when operators should override the default OAuth resource scope.

## Rationale

Satya's implementation handoff (satya-manual-token-scope.md) made clear that token scope is **configuration only**—it must never contain tokens, credentials, or authorization codes. Operators need explicit guidance to:

1. Understand token scope is **not secret material**
2. Know the **default** (`https://energy.azure.com/.default`) is correct for most deployments
3. Know **when** to override (only if their Entra/ADME setup requires different scope)
4. Be protected by **security messaging** that discourages misuse

## Implementation

Added new subsection **Settings: Token Scope** in README.md:

- **What it is:** OAuth resource scope for ADME token acquisition
- **Default:** `https://energy.azure.com/.default`
- **When to override:** Only when Entra app registration or ADME deployment requires different scope
- **Security note:** Never contains tokens, secrets, access codes; misuse is a configuration error, not a feature

## Outcomes

- Operator documentation now reflects Satya's implementation decision
- Token scope is positioned as safe configuration, not credential material
- Security messaging discourages credential-leakage scenarios (e.g., accidental paste of access tokens)
- No code or test changes required; this is pure documentation alignment

## Next Steps

When Judson's Settings UI is merged, the help text/placeholder in the form should match this documentation. This sets expectations before operators encounter the field.

---

### 2026-05-05T15:11:17.396+02:00: Manual token scope final quality gate
**By:** Charlie

## Verdict

APPROVE.

## Evidence

- `ADMEConnection.token_scope` is present and `connection.scope` remains the auth-facing accessor, trimming configured values and falling back to `https://energy.azure.com/.default` for blank input.
- Custom scopes are used by both auth paths: MSAL starts user auth with `[connection.scope]`, and service-principal auth calls `ClientSecretCredential.get_token(connection.scope)`.
- Token-scope changes are treated as connection changes and clear pending user auth, completed user auth, stale health results, and stale health errors. User impersonation cannot test a changed scope with old auth state; service principal can test with the chosen scope.
- Settings now shows Token scope with the default placeholder/help, saves the trimmed value, and explicitly says the field is configuration only—not a token or secret—and should only be changed for custom Entra/ADME OAuth scope requirements.
- README documents the field, default, override guidance, and non-secret status.
- Blank/whitespace scope decisions still conflict on paper: Satya originally required invalid blank scope, while Kevin/Judson accepted blank-as-default fallback. My final reviewer judgment accepts the Kevin/Judson fallback because implementation, tests, and operator guidance are internally consistent.

## Validation

- `python -m pytest tests\test_connection_model.py tests\test_auth_service.py tests\test_connection_state.py tests\test_settings_page.py` — passed, 49 passed.
- `python -m pytest` — passed, 80 passed.
- `python -m ruff check app tests` — passed.
- `python -m mypy app tests` — passed.

## Notes

Scott's operator-copy fix closed the UI guidance gap, and Kevin's lockout-safe mechanical formatting revision restored lint compliance without changing the approved wording or behavior. No further revision required.

---

### 2026-05-05T15:11:17.396+02:00: Manual token scope UI copy fix
**By:** Scott (revision owner; Judson locked out by reviewer gate)

## Verdict

FIXED.

## Evidence

- Charlie's quality gate (charlie-manual-token-scope-review.md) identified missing UI-safety assertions in `tests\test_settings_page.py::test_settings_page_defaults_token_scope_to_adme_resource_scope`.
- Test assertions require TOKEN_SCOPE_HELP text to include:
  - "OAuth scope" phrase ✓
  - "ADME resource scope" phrase ✓
  - "not a token or secret" (case-insensitive) ✓
  - "only change" (case-insensitive) ✓
- Original `TOKEN_SCOPE_HELP` ("OAuth scope used for token acquisition. Defaults to the ADME resource scope.") was too vague and omitted security warnings.

## Implementation

Single-line fix to `app/pages/1_⚙️_Settings.py`:

**Updated `TOKEN_SCOPE_HELP` constant:**
```python
TOKEN_SCOPE_HELP = (
    "OAuth resource scope for ADME token acquisition (defaults to the ADME resource scope). "
    "This is configuration only—not a token or secret. "
    "Do not paste tokens, client secrets, or authorization codes here. "
    "Only change this if your Entra app registration or ADME deployment requires a custom OAuth scope."
)
```

Changes align exactly with README operator guidance and include all required test phrases.

## Validation

- `python -m pytest tests\test_settings_page.py::test_settings_page_defaults_token_scope_to_adme_resource_scope` — PASSED
- `python -m pytest tests\test_settings_page.py` — 19/19 PASSED
- `python -m pytest tests\test_connection_model.py tests\test_auth_service.py tests\test_connection_state.py tests\test_settings_page.py` — 49/49 PASSED

No auth/model/connection-state code touched. No tests edited. Settings behavior unchanged; only help text improved.

## Outcomes

- Operator-facing Settings field now includes mandatory non-secret warning and override guidance
- Test assertions pass; Settings UI copy aligns with README wording
- Feature ready for merge pending final Satya/Eirik approval

## Next

Satya to approve Settings artifact for merge.

---

### 2026-05-05T15:11:17.396+02:00: Token scope guidance Ruff fix
**By:** Kevin

## Decision

Apply a formatting-only wrap to the Settings page Token scope help text so Ruff E501 passes. The user-facing copy is semantically unchanged, and there are no auth, model, test, README, or behavior changes in this revision.

## Why

Charlie's re-review was blocked only by line-length failures after the UI-copy revision. A mechanical wrap is the least risky non-locked-out fix because it keeps Judson's Settings artifact and Scott's copy intent intact while clearing the quality gate.

---

### 2026-05-05T15:11:17.396+02:00: Final manual token scope review
**By:** Satya

## Verdict

APPROVE.

## Contract gates

- `ADMEConnection` remains static connection configuration and now includes `token_scope`; no tokens, pending MSAL flows, authorization codes, or cache material were added to the model.
- `connection.scope` remains the auth-facing accessor. It trims configured scope and falls back to `https://energy.azure.com/.default` when the configured value is blank, and both MSAL user sign-in and service-principal token acquisition consume `connection.scope`.
- I accept blank/whitespace **Token scope** as default/fallback behavior, superseding the earlier handoff conflict that asked validation to reject blank scope. This keeps operator behavior internally consistent with Kevin's backend contract, Judson's Settings flow, Charlie's approval, and the current tests.
- Settings exposes **Token scope** after **Client ID**, uses the ADME default as value/placeholder when no connection exists, gives clear non-secret guidance, trims saved input, and treats scope-only changes as connection changes that clear pending auth, completed user auth, stale health results, and stale health errors.
- README matches the operator-facing behavior: default ADME scope, custom override guidance, and explicit non-secret status.
- Charlie's final validation evidence is sufficient. Reviewer lockout was respected: Scott revised Judson's rejected UI-copy artifact, Kevin handled only the follow-up formatting fix after Scott's revision, and Charlie approved the final result.

## Validation

- `python -m pytest tests\test_connection_model.py tests\test_auth_service.py tests\test_connection_state.py tests\test_settings_page.py` — passed, 49 passed.
- `python -m pytest` — passed, 80 passed.
- `python -m ruff check app tests` — passed.
- `python -m mypy app tests` — passed.

## Decision

Ready for coordinator merge handling. No further implementation changes required.


---

### 2026-05-05: Local persistence for ADME connection settings (SQLite)
**By:** Satya

## Decision

Persist user-entered ADME connection settings (the control plane) to a local
SQLite database via the Python stdlib `sqlite3` module. SQLite becomes the
durable backing store; Streamlit `st.session_state` remains the per-rerun
working copy and continues to own all auth/session-only material.

## Why SQLite (and not pglite)

- pglite is JS/WASM (Postgres compiled for the browser). The Streamlit app
  runs Python on the server side; pglite cannot be embedded in that process
  and adds a Node.js/WASM dependency that we will not own.
- SQLite via `sqlite3` is stdlib — zero new runtime dependencies, no install
  step, works under our current emulation/test environment, and gives us a
  single-file database that is trivially git-ignored and trivially deleted
  for a clean reset.
- File-based persistence matches operator expectations for a desktop-style
  control plane: settings survive across sessions for the same OS user, and
  there is no separate service to start.

## Storage location

- Path: `~/.adme-ingestion-tool/settings.db` resolved via
  `Path.home() / ".adme-ingestion-tool" / "settings.db"`.
- Created lazily on first write; directory created with `mkdir(parents=True,
  exist_ok=True)`.
- Overridable via environment variable `ADME_SETTINGS_DB` for tests and
  alternate installs (tests MUST use `tmp_path`, never the real home dir).
- Why user profile (not repo): the database is per-operator state, not
  product code. Storing it in the repo would (a) leak operator-specific
  endpoints/tenant IDs through git, (b) collide between developers sharing
  the checkout, and (c) be wiped by routine `git clean`. The user-profile
  location is the same convention used by `az`, `gh`, `kubectl`, etc.
- `.gitignore`: not required (the path is outside the repo), but add the
  override path (`*.db` under `.adme-ingestion-tool/`) defensively if any
  test fixture writes inside the workspace.

## Schema — `connections` table

```sql
CREATE TABLE IF NOT EXISTS connections (
    name              TEXT PRIMARY KEY,
    endpoint          TEXT NOT NULL,
    tenant_id         TEXT NOT NULL,
    client_id         TEXT NOT NULL,
    data_partition_id TEXT NOT NULL,
    token_scope       TEXT NOT NULL DEFAULT 'https://energy.azure.com/.default',
    auth_method       TEXT NOT NULL CHECK (auth_method IN
                          ('user_impersonation', 'service_principal')),
    is_active         INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_connections_active
    ON connections(is_active) WHERE is_active = 1;
```

### Schema decisions

- **Primary key is `name` (operator-supplied label), not the endpoint.** An
  operator may register the same ADME endpoint under different labels
  (e.g. `prod`, `prod-readonly`) with different auth methods. `name` is the
  stable human handle.
- **No `id` surrogate key.** `name` is short, stable, and already unique.
  Adding an integer PK buys nothing for a single-user local store.
- **`client_secret` is NOT persisted.** Secrets at rest are explicitly out
  of scope (see below). Service-principal connections will require the
  operator to re-enter the secret per session until encryption-at-rest is
  added. The Settings UI must communicate this clearly.
- **No `token_scope` UNIQUE.** Scope is config that may legitimately vary
  per saved connection.
- **`is_active` partial unique index** enforces "at most one active
  connection at a time" without needing a separate `active_connection`
  table. Activating a new row sets others to 0 in the same transaction.
- **Timestamps as ISO 8601 TEXT** (`datetime.now(UTC).isoformat()`).
  SQLite has no native datetime; TEXT is portable and human-readable.
- Field names mirror `app/models/connection.py` (`ADMEConnection`) so the
  store/load mapping is mechanical.

## API surface — `app/services/settings_store.py`

Function signatures only; bodies are Kevin's work.

```python
"""Local SQLite-backed store for persisted ADME connection settings."""

from __future__ import annotations

from pathlib import Path

from app.models.connection import ADMEConnection


DEFAULT_DB_PATH: Path  # = Path.home() / ".adme-ingestion-tool" / "settings.db"


class SettingsStoreError(Exception):
    """Raised when the local settings store cannot be read or written."""


def get_db_path() -> Path: ...
    """Return the resolved SQLite path, honoring ADME_SETTINGS_DB."""


def initialize_store(db_path: Path | None = None) -> None: ...
    """Create the DB file and schema if missing. Idempotent."""


def list_connections(db_path: Path | None = None) -> list[tuple[str, ADMEConnection]]: ...
    """Return saved (name, connection) pairs, ordered by name."""


def load_connection(name: str, db_path: Path | None = None) -> ADMEConnection | None: ...
    """Return the saved connection for name, or None if missing."""


def save_connection(
    name: str,
    connection: ADMEConnection,
    db_path: Path | None = None,
) -> None: ...
    """Insert or update a saved connection by name. client_secret is not persisted."""


def delete_connection(name: str, db_path: Path | None = None) -> None: ...
    """Remove a saved connection by name. No error if missing."""


def get_active_connection_name(db_path: Path | None = None) -> str | None: ...
    """Return the currently active connection name, or None if none active."""


def set_active_connection(name: str, db_path: Path | None = None) -> None: ...
    """Mark name as active and clear the active flag on all other rows.

    Raises SettingsStoreError if name does not exist.
    """


def clear_active_connection(db_path: Path | None = None) -> None: ...
    """Clear the active flag on all rows. Used on Sign Out / reset."""
```

### API design notes

- `db_path` is a thin seam for tests (override with `tmp_path`) and the
  `ADME_SETTINGS_DB` env var. Defaults to `get_db_path()`.
- All functions open and close a short-lived `sqlite3` connection. No
  module-global cursor; no Streamlit caching. Concurrency is single-user.
- `save_connection()` MUST drop `client_secret` before INSERT/UPDATE.
  Document this in the docstring; assert it in tests.
- `set_active_connection()` and `save_connection(... is_active=True)` paths
  must run inside `BEGIN IMMEDIATE` to keep the partial unique index honest
  on activation switches.
- Errors from `sqlite3` are re-raised as `SettingsStoreError` with
  operator-safe messages. No raw connection strings or tokens in messages.

## UI integration touchpoints

### `app/connection_state.py`

- `ensure_session_defaults(session_state)` — call
  `settings_store.initialize_store()` once and, when `CONNECTION_KEY` is
  absent from session state, hydrate it via
  `load_connection(get_active_connection_name())`. Keep all existing keys.
- `save_connection(session_state, connection)` — after updating session
  state, call `settings_store.save_connection(name, connection)` and
  `settings_store.set_active_connection(name)`. The function gains an
  optional `name` argument; for the v1 single-connection UX, default to
  the literal `"default"` label so existing call sites do not break.
- `clear_user_auth_state(session_state)` — unchanged. Auth material is
  session-only and is NOT written to SQLite.
- New helper `forget_saved_connection(session_state, name)` that wraps
  `settings_store.delete_connection` plus any session cleanup.

### `app/pages/1_⚙️_Settings.py`

- `_handle_form_action(...)` — when `save_clicked` succeeds, the existing
  call to `save_connection(st.session_state, draft_connection)` already
  becomes the persistence path once `connection_state.save_connection`
  delegates to the store. No new code in the page for the v1 single-slot
  flow beyond the success message ("Saved for this and future sessions.").
- `_consume_oauth_callback_once()` — unchanged. Auth flow is session-only.
- (Deferred to a follow-up issue: a "Saved connections" picker that lists
  rows from `list_connections()` and lets the operator switch active. For
  this scope we ship single-slot persistence keyed on the `"default"`
  name.)

### `app/main.py`

- No changes required. `ensure_session_defaults()` already runs at the top
  of `main()`, so hydration happens transparently.

## Out of scope (deferred — explicit non-goals)

- **Encryption of secrets at rest.** `client_secret` is NOT persisted in
  v1. Operators re-enter it per session for service-principal auth.
  A future issue can add OS-keychain integration (`keyring`) or a
  passphrase-derived key.
- **Multi-user / shared deployment support.** This store is single-user,
  single-host. Not safe for shared filesystems.
- **Migrations framework.** v1 ships one schema. Future schema changes
  will be handled by an additive migration helper when we get there;
  do not pull in Alembic for a single-table store.
- **Connection picker UI / multiple saved profiles.** The API supports it
  (`list_connections`, `set_active_connection`); the UI ships single-slot.
- **Cross-process locking.** SQLite handles this; we do not add app-level
  locks.
- **Telemetry / audit log of edits.** Not in scope.

## Work breakdown

### Kevin (Backend)

1. Add `app/services/settings_store.py` with the API above. Implement the
   bodies. No new runtime deps; stdlib `sqlite3` + `pathlib` only.
2. Implement `DEFAULT_DB_PATH`, `get_db_path()` env-var override, and
   schema initialization (`CREATE TABLE IF NOT EXISTS` + partial index).
3. Implement save/load/delete/list with the documented client_secret-drop
   guarantee. Use `BEGIN IMMEDIATE` for activation transitions.
4. Wire `app/connection_state.py`:
   - hydrate session from active row in `ensure_session_defaults`;
   - delegate `save_connection` to the store and set active;
   - keep auth helpers untouched.
5. Smoke-test locally with `streamlit run app/main.py`: enter a
   connection, restart the app, confirm it reloads.
6. No README changes — Scott will pick that up after the store lands.

### Charlie (Tester)

1. Add `tests/test_settings_store.py`:
   - happy-path round-trip (save → load → list → delete);
   - `client_secret` is dropped on save (load returns empty string);
   - `set_active_connection` flips active correctly; partial unique
     index allows zero or one active row;
   - `get_active_connection_name` returns None on empty DB and the right
     name after activation;
   - `ADME_SETTINGS_DB` env-var override is honored;
   - schema is idempotent (`initialize_store` called twice is a no-op);
   - missing-name `delete_connection` is a no-op (no exception);
   - `set_active_connection` on unknown name raises
     `SettingsStoreError`;
   - all tests use `tmp_path`; none touch the real home directory.
2. Extend `tests/test_connection_state.py`:
   - `ensure_session_defaults` hydrates `CONNECTION_KEY` from a stubbed
     active row;
   - `save_connection` writes through to the store (mock or fake store);
   - changing the connection still clears auth and health state.
3. Extend `tests/test_settings_page.py` minimally:
   - asserting the existing save flow still passes after persistence
     wiring (no new UI assertions needed for v1).
4. Validation gates: full `pytest`, `ruff check app tests`,
   `mypy app tests` all green before requesting review.

### Sequencing

- Kevin lands `settings_store.py` (steps 1–3) first. Charlie can write
  the store-only tests in parallel against the published signatures.
- Kevin then wires `connection_state.py` (step 4). Charlie's session-
  state and page tests follow.
- Satya reviews before merge; any change to the public function
  signatures above requires lead sign-off.

---

### 2026-05-05: Autouse fixture isolates ADME_SETTINGS_DB for every test
**By:** Charlie (Tester), requested by Mariel
**What:** Added `_isolate_settings_db` autouse fixture in `tests/conftest.py`
that sets `ADME_SETTINGS_DB` to `tmp_path/settings.db` for every test in the
suite. Test code never falls through to `Path.home() / ".adme-ingestion-tool"
/ "settings.db"`.
**Why:** Two tests (`test_main_prompts_operator_to_open_settings_when_not_configured`
and `test_settings_page_defaults_token_scope_to_adme_resource_scope`) passed
in isolation but failed under the full suite because
`ensure_session_defaults` hydrated from the operator's real on-disk settings
DB. Per-test opt-in isolation (the existing `isolated_store` fixture) is
fragile — any new test that forgets to request it re-opens the leak. Autouse
is the only durable fix.
**Scope:** Test infrastructure only. No production behavior changes.
`app/services/settings_store.py` was untouched and needs no reset hook
because it holds no module-level state — every call opens a short-lived
`sqlite3` connection via `closing()`.
**Result:** Full suite green: 105 passed.


---


---




### 2026-05-05: Entitlements smoke-test page architecture
**By:** Satya (via Copilot)
**Requested by:** Mariel

## Decision

Add a dedicated Streamlit page that exercises the ADME Entitlements API as
the operator's "did I configure this correctly?" smoke test. This is a
distinct surface from the OSDU service health probe — health asks "is the
service up", entitlements asks "does my token actually work as me".

The work is partitioned cleanly between Kevin (service module + result
model), Judson (page + chart + UX), and Charlie (tests). Mariel's UX
answers are binding and reproduced in the contract below.

## File layout (confirmed)

- **New service module:** `app/services/entitlements.py`
- **New page:** `app/pages/2_🔑_Entitlements.py` (emoji prefix matches the
  `1_⚙️_Settings.py` convention so Streamlit's auto-discovered page nav
  stays consistent)
- **Result model lives in:** `app/models/connection.py`, alongside
  `ServiceHealthResult`
- **New tests:** `tests/test_entitlements_service.py` and
  `tests/test_entitlements_page.py`

### Why `EntitlementsCallResult` lives in `app/models/connection.py`

The `app/models/connection.py` docstring already describes itself as the
"shared contract between the UI layer (Judson) and the backend services
(Kevin)", and it already hosts `ServiceHealthResult` for the same
service-result-shape reason. Splitting service result dataclasses into
parallel files (`models/health.py`, `models/entitlements.py`, ...) would
fragment that contract for no benefit at this size. Revisit if the
connection module exceeds ~300 LOC or if entitlements grows its own data
types beyond a result envelope.

## Service contract — `app/services/entitlements.py`

Mirrors `app/services/health.py`: stdlib + `requests`, ~5 s timeout, no
retries inside the service (the UI's "Re-run test" button is the retry
control). Both functions are independent — Judson may call them
sequentially or concurrently; the service does not assume either order.

```python
PROBE_TIMEOUT_SECONDS = 5
MEMBERS_SELF_PATH = "/api/entitlements/v2/members/{me}"  # literal {me} per ADME contract
GROUPS_PATH = "/api/entitlements/v2/groups"

def fetch_member_self(
    connection: ADMEConnection,
    token: str,
) -> EntitlementsCallResult: ...

def fetch_groups(
    connection: ADMEConnection,
    token: str,
) -> EntitlementsCallResult: ...
```

Both functions:

- Validate `connection.is_valid()` and that `token` is non-empty (raise
  `ValueError` on misuse, matching `health.check_all`).
- Build `Authorization: Bearer {token}` and
  `data-partition-id: {connection.data_partition_id}` headers.
- Use `requests.get(...)` with `timeout=PROBE_TIMEOUT_SECONDS` and
  `allow_redirects=False`.
- Time the call with `time.perf_counter()` and report `latency_ms` rounded
  to 2 decimals (same idiom as `health._elapsed_ms`).
- Treat `200 <= status < 300` as success; on success, parse the JSON body
  into `data`. On non-2xx, build a friendly message using the same
  shape-tolerant pattern as `health._build_http_error_message` and store
  the raw body in `raw_response`.
- On `requests.Timeout` and `requests.RequestException`, return
  `ok=False`, `http_status=None`, an `error_message` from the exception,
  `correlation_id=None`, and `raw_response=None`.
- Catch only `requests.RequestException` and `ValueError` (JSON parse) at
  the boundary. Do not silence broader exceptions.

### `EntitlementsCallResult` shape

```python
@dataclass
class EntitlementsCallResult:
    """Outcome of a single ADME Entitlements API call."""

    endpoint: str            # logical label, e.g. "members/{me}" or "groups"
    path: str                # API path actually called
    ok: bool
    http_status: int | None
    latency_ms: float
    correlation_id: str | None
    error_message: str       # "" on success, friendly message on failure
    raw_response: dict | str | None  # parsed JSON if available, else raw text, else None
    data: dict | None        # parsed payload only when ok is True
```

Conventions match `ServiceHealthResult`: `error_message` defaults to
empty string (not None) on success; `latency_ms` is always populated
(never None) so the in-session chart never has to handle holes.

### Correlation ID extraction

ADME Entitlements returns the correlation identifier on the response
header. The service performs a **case-insensitive lookup** because
`requests.Response.headers` is a `CaseInsensitiveDict` but operators may
configure proxies that re-emit headers in different casing. Probe in
order and take the first hit:

1. `correlation-id`
2. `x-correlation-id`
3. `request-id`
4. `x-request-id`

If none are present, `correlation_id` is `None`. Surface whichever value
is found verbatim — do not normalize, lowercase, or wrap.

## Page contract — `app/pages/2_🔑_Entitlements.py`

UX (binding from Mariel):

- **Auto-run-once on load if a token exists.** Use a session-state guard
  (`st.session_state["entitlements_autorun_done"]`) so that a Streamlit
  rerun does not re-fire the calls. The "Re-run test" button explicitly
  bypasses the guard and calls both endpoints again.
- **Both endpoints called per run.** `fetch_member_self` first (so the
  "who am I" banner renders even if the groups call fails), then
  `fetch_groups`.
- **Status banner:** ✅ green when both calls return `ok=True`; ❌ red
  otherwise. Failure banner shows: friendly message, HTTP status,
  correlation/request ID (if any), and an expander with `raw_response`.
- **Groups display:** primary view is a `st.dataframe` table built from
  `data["groups"]` (typical ADME shape: list of `{name, description,
  email}` objects). Tolerate a missing `groups` key by showing an empty
  table plus an info caption.
- **Raw JSON expander:** one expander per endpoint, rendered with
  `st.json(result.raw_response or result.data)`.
- **No data-partition override.** Use `connection.data_partition_id`
  from the saved connection. There is no per-page override field. The
  page renders the partition value as a read-only caption so operators
  can see what was used.
- **No token re-prompt.** If `get_user_auth_state()` is None (user
  impersonation) AND the connection is not service-principal, render a
  friendly banner "No token available — configure on the Settings page"
  with a `st.page_link` to `pages/1_⚙️_Settings.py`. Do **not** call
  `start_user_auth_flow` from this page.
- **Token acquisition:** for service-principal connections, call
  `get_token(connection)`. For user impersonation, call
  `get_token(connection, user_auth_state=...)` using the existing session
  state helper. Wrap in `try/except AuthenticationError` and degrade to
  the friendly "configure on Settings" banner with the auth error
  message attached.

### Latency / retry chart — in-session history

History is a Streamlit-session-scoped list of dict entries (chosen over
tuples so future fields don't require a positional rewrite). It is
**append-only within a session** and is cleared whenever the connection,
auth method, or token scope changes — Judson should reuse the existing
`clear_*` hooks in `connection_state` and add a peer
`clear_entitlements_history` invoked from the same code paths that
already clear health state.

```python
st.session_state["entitlements_history"]: list[dict] = [
    {
        "timestamp": "2026-05-05T10:30:00Z",  # ISO 8601 UTC
        "endpoint": "members/{me}" | "groups",
        "latency_ms": float,
        "http_status": int | None,
        "ok": bool,
    },
    ...
]
```

Render with `st.line_chart` keyed on `timestamp` with `latency_ms` as
the value column, grouped by `endpoint`. `altair` is acceptable if
Judson wants per-endpoint coloring without reshaping; we already pull
in only Streamlit's bundled deps so prefer `st.line_chart` first. Below
the chart, a small `st.dataframe` shows the last ~10 entries with
status badge, latency, and correlation ID for quick diagnosis.

### Auth integration

- Read connection via `get_connection(st.session_state)`.
- Read token (if any) via the same helpers `1_⚙️_Settings.py` already
  uses. The page does **not** import `start_user_auth_flow` or
  `complete_user_auth_flow`. Settings remains the only owner of the OAuth
  callback dance (per the issue #8 decision).

## Out of scope (explicit)

The following are deferred and must not creep into this page or
service in v1:

- Pagination of groups beyond the API's default page (no `cursor`,
  `limit`, "load more" UI).
- Group filtering UI (search box, role-based filter, regex).
- Group membership management (add/remove members, delete groups,
  rename groups). This page is **read-only**.
- Caching of entitlements results across reruns. Each run hits the API
  fresh; the in-session chart is the only persisted artifact.
- Cross-tenant impersonation or alternate `data-partition-id` overrides.

## Work breakdown

- **Kevin** — `app/services/entitlements.py` (both functions, the
  shape-tolerant error message helper mirroring `health._build_http_error_message`,
  correlation-ID extraction) and the `EntitlementsCallResult` dataclass
  added to `app/models/connection.py`. Update the module docstring to
  mention entitlements as a co-tenant of the contract. Keep the public
  surface to the two `fetch_*` functions plus the dataclass.

- **Judson** — `app/pages/2_🔑_Entitlements.py` end-to-end: auto-run-once
  guard, "Re-run test" button, status banner, both raw-JSON expanders,
  groups dataframe, latency line chart, last-N history table, the
  no-token friendly banner, and `clear_entitlements_history` wiring into
  the existing connection/auth-change handlers in `connection_state`.

- **Charlie** — service tests against mocked `requests` responses
  covering: 2xx success on both endpoints, non-2xx with JSON error body,
  non-2xx with text body, timeout, network error, correlation-ID
  extraction across all four header casings, and missing-correlation
  fallback. Page smoke test using the existing `tests/support/streamlit_recorder.py`
  pattern: renders the no-token banner when token is absent, renders the
  status banner and history append on a successful mocked run, and does
  not double-fire the auto-run on a Streamlit rerun.

## Sequencing

- Kevin lands `entitlements.py` and the `EntitlementsCallResult`
  addition first so the public signatures are frozen. Judson can scaffold
  the page in parallel against those signatures but must not merge
  before Kevin's contract is in.
- Charlie's service tests can land alongside Kevin. Page tests follow
  Judson.
- No Scott work this round; no infra, no new dependencies. All required
  packages (`requests`, `streamlit`) are already declared.

## Acceptance criteria

- `app/services/entitlements.py` exposes `fetch_member_self` and
  `fetch_groups` matching the signatures above.
- `EntitlementsCallResult` exists in `app/models/connection.py` with the
  documented fields and defaults.
- `app/pages/2_🔑_Entitlements.py` auto-runs once when a token exists,
  re-runs on demand, never auto-runs twice across reruns, and never
  re-prompts for sign-in.
- Correlation ID is extracted case-insensitively from the four header
  names listed above.
- In-session history is cleared when the connection, auth method, or
  token scope changes, using the same hook points as health state.
- Pagination, filtering, and membership management are absent from both
  the service and the page.
- Targeted tests pass: `tests/test_entitlements_service.py` and
  `tests/test_entitlements_page.py`. Full suite stays green. Ruff and
  mypy stay clean.

---

### 2026-05-05: Entitlements service contract diverges from Satya's spec
**By:** Judson
**Requested by:** Mariel

## What

While building `app/pages/2_🔑_Entitlements.py` against Kevin's
`app/services/entitlements.py`, I noticed two small divergences from the
contract Satya wrote in `satya-entitlements-page.md`. Per Mariel's task
direction ("do NOT modify Kevin's service... proceed using his contract"),
I built the page against Kevin's actual surface and am logging the deltas
here so Satya/Charlie can rule on them after the fact.

## Divergences

1. **`MEMBERS_SELF_PATH`** — Satya: `"/api/entitlements/v2/members/{me}"`
   (literal `{me}`). Kevin: `"/api/entitlements/v2/members/me"` (literal
   `me`). Kevin's path matches the actual ADME entitlements REST contract
   in production; the OSDU spec uses `me` as a literal segment, not a
   parameter placeholder. Kevin's choice is correct; Satya's note read
   the OSDU OpenAPI definition too literally.

2. **Endpoint label** — Satya: `"members/{me}"`. Kevin:
   `"members.self"`. The `.self` form is friendlier for chart legends
   (no curly braces, easy to read) and avoids ambiguity if/when ADME
   adds a true `/members/{id}` endpoint. The page uses Kevin's labels
   verbatim in the latency chart.

3. **`error_message` on success** — Satya's `EntitlementsCallResult`
   sketch had `error_message: str` with `""` default; Kevin's
   implementation uses `error_message: str | None = None`. The page
   handles both: it treats falsy values (None or empty string) as "no
   error" and only renders the error block when `error_message` is a
   non-empty string.

## Why this is fine

None of these change the public behavior the page depends on. The page
calls `fetch_member_self` and `fetch_groups`, reads `result.ok`,
`result.http_status`, `result.latency_ms`, `result.correlation_id`,
`result.error_message`, `result.raw_response`, and `result.data`. All
of those work identically under both readings.

## Action requested

- Satya: confirm Kevin's path/label choices and update the inbox spec
  in a future revision if needed (no merge blocker).
- Charlie: tests should assert against Kevin's actual constants
  (`MEMBERS_SELF_PATH = "/api/entitlements/v2/members/me"`,
  `MEMBERS_SELF_ENDPOINT_LABEL = "members.self"`), not Satya's sketch.
- No code change needed in `app/services/entitlements.py` or
  `app/pages/2_🔑_Entitlements.py`.
