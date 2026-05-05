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

