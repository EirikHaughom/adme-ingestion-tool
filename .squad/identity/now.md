---
updated_at: 2026-04-26T06:51:32Z
focus_area: Issue #8 design complete — app-returning auth flow
active_issues:
  - "#8: Design app-returning auth login flow (design complete, awaiting implementation planning)"
---

# What We're Focused On

All prior sprint issues (#1-#7) remain approved and closed:
- #1: Streamlit scaffolding ✓
- #2: Welcome/settings pages + health validation ✓
- #3: Streamlit import-path fix ✓
- #4: Interactive browser login (DeviceCodeCredential → InteractiveBrowserCredential) ✓
- #5: Interactive auth callback fix (public client ID for token exchange) ✓
- #6: Tenant-compatible auth (customer app registration + hardcoded ADME scope) ✓
- #7: Auth redirect behavior clarification (explicit localhost:8400 + Settings guidance) ✓

Current open issue:
- #8: Design app-returning auth login flow - design complete
  - Current `InteractiveBrowserCredential` flow cannot redirect back into Streamlit.
  - Planned direction: app-managed MSAL auth code + PKCE flow with redirect URI on `http://localhost:8501`.
  - Implementation has not started yet.
