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

## Issue #8 Auth Flow - Team Completion (2026-05-05)

**Status:** ✅ COMPLETE & VALIDATED

All team members successfully completed assigned work for MSAL auth integration:
- Satya: Lead review and final validation
- Kevin: Auth-service implementation
- Scott: Documentation and README updates
- Judson: Settings page integration
- Charlie: Quality gate and regression coverage

Final outcome: Full test suite passed (70), Ruff clean, mypy clean. Ready for merge.
## 2026-05-05: Manual Token Scope Configuration (Complete)

**Status:** COMPLETE
**Decision:** Manual token scope configuration merged to decisions.md
**Outcome:** ADMEConnection now includes token_scope field with ADME default fallback. Settings UI exposes non-secret Token scope field. Both auth paths (user and service principal) consume connection.scope. All validation passed: pytest 80, ruff, mypy.
---

## 2026-05-05T10:30:00Z — Cross-agent note from Scribe

The team shipped a new Entitlements smoke-test page and service today
(pp/services/entitlements.py, pp/pages/2_🔑_Entitlements.py,
EntitlementsCallResult in pp/models/connection.py). Two probes
now exist for deployment-health work you may pick up later:

- pp/services/health.py — OSDU service health (already in place)
- pp/services/entitlements.py — etch_member_self + etch_groups,
  same shape: EntitlementsCallResult with ok, http_status,
  latency_ms, correlation_id, rror_message,aw_response,
  data. Mirrors ServiceHealthResult exactly.

If/when you wire deployment readiness checks (post-deploy smoke,
synthetic monitoring), both modules are safe to call headlessly:
stdlib +equests, ~5s timeout, no retries inside the service.
Correlation-ID extraction is case-insensitive across correlation-id,
x-correlation-id,equest-id, x-request-id. No new runtime deps
were added.