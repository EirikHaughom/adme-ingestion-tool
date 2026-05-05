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

