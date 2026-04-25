# Satya Orchestration Log — Issue #5 Design Batch

## Agent Status
- **Role:** Lead
- **Mode:** Design
- **Issue:** #5
- **Timestamp:** 2026-04-25T19:44:06.175+02:00

## Outcome
Diagnosed that interactive browser auth was incorrectly using the ADME confidential-client app ID, causing the post-callback token exchange to fail with AADSTS7000218 / invalid_client. Recommended using the Azure CLI public client ID for InteractiveBrowserCredential while preserving the ADME client ID for scope derivation. Updated issue #5 with the real design status.

## Root Cause Analysis

Interactive browser auth was failing post-callback because:
1. `ADMEConnection.client_id` field serves dual roles:
   - OAuth resource identifier: used for scope derivation (`{client_id}/.default`)
   - Authenticating client: passed to credential instantiation
2. ADME instance app registration is a **confidential client** (has client secret configured in Azure AD)
3. `InteractiveBrowserCredential` doesn't send `client_secret` by design (targets public clients)
4. Azure AD rejects the auth-code exchange: confidential client without secret = invalid_client = AADSTS7000218

Browser sign-in succeeds because authorization endpoint allows user authentication. Failure occurs during token exchange when Azure AD demands credentials InteractiveBrowserCredential cannot provide.

## Service Principal Unaffected
`ClientSecretCredential` sends both `client_id` and `client_secret`, satisfying Azure AD for confidential clients. Scope `{client_id}/.default` resolves to app's permissions, returning token with correct audience.

## Recommended Fix (Minimal, No UI Changes)

Use **Azure CLI well-known public client ID** (`04b07795-a710-4f9e-9640-a91e60e60e08`) for `InteractiveBrowserCredential`.
Continue using `connection.client_id` exclusively for scope derivation.

```python
AZURE_CLI_PUBLIC_CLIENT_ID = "04b07795-a710-4f9e-9640-a91e60e60e08"

return InteractiveBrowserCredential(
    client_id=AZURE_CLI_PUBLIC_CLIENT_ID,
    tenant_id=connection.tenant_id,
)
```

### Why This Works
- Azure CLI's app registration is a **public client** — no secret required during auth-code exchange
- User authenticates as themselves in browser (delegated permissions)
- Token's audience (`aud`) set to `connection.client_id` because scope is `{connection.client_id}/.default`
- ADME instances accept tokens issued to Azure CLI client by default
- Azure CLI's public client is trusted by all Azure AD tenants

## Optional Future Enhancement
Add optional `interactive_client_id` field to `ADMEConnection` for environments that block Azure CLI client:
1. When populated, use instead of Azure CLI default
2. Surface in Settings form only for USER_IMPERSONATION
3. Not required for initial fix

## Files to Change
- `app/services/auth.py`: Define constant, update _build_credential
- `tests/test_auth.py`: Update assertion for public client ID
- `tests/test_auth_service.py`: Update assertion for public client ID

No changes needed:
- `app/models/connection.py`
- `app/pages/1_⚙️_Settings.py`
- `tests/test_settings_page.py`

## Status
✓ Design approved — ready for implementation
