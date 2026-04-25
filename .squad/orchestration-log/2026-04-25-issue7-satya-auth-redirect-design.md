# Orchestration Log: Issue #7 Design Phase
## Auth Redirect After Interactive Sign-In

**Phase:** Design  
**Agent:** Satya (Lead)  
**Timestamp:** 2026-04-25T21:46:41Z  
**Issue:** [#7 — Align interactive auth redirect with Streamlit app URL](https://github.com/EirikHaughom/adme-ingestion-tool/issues/7)

---

## Root Cause Analysis

`InteractiveBrowserCredential` from azure-identity 1.22.0 starts an ephemeral HTTP server on localhost (default port 8400) to capture the OAuth2 authorization code after user sign-in. The SDK **must** receive the code on that server to exchange it for a token. Redirecting the user to Streamlit's port 8501 would break the flow because Streamlit has no handler for the OAuth `?code=` parameter.

**Key Finding:** This is a fundamental constraint of the authorization code flow with a local listener. It applies equally to MSAL Python's `acquire_token_interactive`.

---

## Current State (Before Fix)

```python
# app/services/auth.py:81-84
InteractiveBrowserCredential(
    client_id=connection.client_id,
    tenant_id=connection.tenant_id,
)
```

No explicit `redirect_uri` is passed, so the SDK uses its default (http://localhost:8400 per Azure SDK docs). This port **must** be registered in the Azure AD app registration.

---

## Recommended Fix (Two Parts)

### Part 1: Better UI Guidance
Update help text in `app/pages/1_⚙️_Settings.py`:
- **New guidance:** "A new browser tab will open for sign-in. After completing sign-in, close that tab and return here."
- The Streamlit spinner already displays while waiting; results appear automatically once `get_token()` returns.

### Part 2: Explicit Redirect URI
Pass `redirect_uri="http://localhost:8400"` explicitly to `InteractiveBrowserCredential`:

```python
InteractiveBrowserCredential(
    client_id=connection.client_id,
    tenant_id=connection.tenant_id,
    redirect_uri="http://localhost:8400",
)
```

**Benefits:**
- Makes the port deterministic and self-documenting
- Ensures it matches the app registration (already lists http://localhost:8400)
- Removes reliance on SDK defaults, which could change between versions

---

## Files to Change

| File | Owner | Change |
|------|-------|--------|
| `app/services/auth.py` | Kevin | Add `redirect_uri="http://localhost:8400"` to `_build_credential()` |
| `app/pages/1_⚙️_Settings.py` | Judson | Update guidance strings in UI |
| `tests/test_auth.py` | Kevin | Assert `redirect_uri` is passed in credential kwargs |
| `tests/test_settings_page.py` | Judson | Assert updated guidance text in UI tests |

---

## Out of Scope

- Do **not** try to use `success_template` or custom success messages — not exposed by `InteractiveBrowserCredential`
- Do **not** replace with raw MSAL calls — adds complexity for marginal UX gain
- Do **not** redirect to Streamlit — it will break authentication

---

## Expected Outcome

After fix:
1. User clicks **Test Connection** on Settings page
2. Streamlit shows spinner: "Authenticating and checking ADME services..."
3. New browser tab opens to Azure AD sign-in
4. After successful login: tab shows "Authentication complete. You can close this window."
5. User closes tab or switches back to Streamlit tab
6. Settings page renders service health results automatically

The guidance text makes step 5 obvious. The explicit `redirect_uri` prevents port drift across SDK versions.

---

## Sign-Off

✅ **Design approved for implementation phase**

Next: Charlie planning review, then Kevin & Judson parallel implementation.
