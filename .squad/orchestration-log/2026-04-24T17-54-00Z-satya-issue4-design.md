# Satya Orchestration Log — Issue #4 Design Batch

## Agent Status
- **Role:** Lead
- **Mode:** Design
- **Issue:** #4
- **Timestamp:** 2026-04-24T19:54:00.751+02:00

## Outcome
Approved the InteractiveBrowserCredential approach as the correct interactive user-login replacement for device-code sign-in, identified the minimal affected files, and updated issue #4 with the real design status.

## Design Decision: Replace Device-Code Login with Interactive Browser Login

**Decision:** Replace `DeviceCodeCredential` with `InteractiveBrowserCredential` from `azure-identity` for the `USER_IMPERSONATION` auth method.

**Rationale:**
- `DeviceCodeCredential` forces unnecessary friction: copy-paste code flow (`Open https://login.microsoft.com/device and enter code`)
- `InteractiveBrowserCredential` opens system browser with standard Entra ID login and redirects back to localhost callback — standard for desktop/locally-run apps
- Direct 1:1 swap: same OAuth 2.0 authorization code grant, better UX

## Affected Files (Minimal)
| File | Changes |
|------|---------|
| `app/services/auth.py` | Import `InteractiveBrowserCredential`; replace constructor; remove `_device_code_prompt_callback` |
| `app/pages/1_⚙️_Settings.py` | Update help text from device-code to browser sign-in |
| `tests/test_auth.py` | Monkeypatch `InteractiveBrowserCredential` instead of `DeviceCodeCredential`; remove callback assertions |
| `tests/test_auth_service.py` | Same monkeypatch and assertion updates |

**No changes needed:**
- `app/models/connection.py` — `AuthMethod.USER_IMPERSONATION` unchanged
- `requirements.txt` / `pyproject.toml` — `azure-identity>=1.19.0` already includes `InteractiveBrowserCredential`

## Implementation Notes

### Code Pattern
```python
from azure.identity import InteractiveBrowserCredential

if auth_method == AuthMethod.USER_IMPERSONATION:
    return InteractiveBrowserCredential(
        client_id=connection.client_id,
        tenant_id=connection.tenant_id,
    )
```
- No `prompt_callback` — browser handles everything
- No `redirect_uri` — defaults to `http://localhost` with ephemeral port

### Runtime Caveats to Preserve
1. **Local-only assumption:** Browser spawning requires local machine; fails on headless servers
2. **Credential cleanup:** Existing `_close_credential()` pattern applies to `InteractiveBrowserCredential`
3. **Error handling:** Same `CredentialUnavailableError`/`ClientAuthenticationError` chain applies
4. **Type annotations:** Update union type from `DeviceCodeCredential | ClientSecretCredential` to `InteractiveBrowserCredential | ClientSecretCredential`

## Status
✓ Design approved — ready for implementation
