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

## Issue #8 Auth Flow - Team Completion (2026-05-05)

**Status:** ✅ COMPLETE & VALIDATED

All team members successfully completed assigned work for MSAL auth integration:
- Satya: Lead review and final validation
- Kevin: Auth-service implementation
- Scott: Documentation and README updates
- Judson: Settings page integration
- Charlie: Quality gate and regression coverage

Final outcome: Full test suite passed (70), Ruff clean, mypy clean. Ready for merge.
