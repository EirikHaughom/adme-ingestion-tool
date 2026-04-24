# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Kevin owns backend services, ADME integrations, and data-handling logic for the control plane.
- Reliability and explicit error handling matter because the app coordinates platform operations, not just passive reporting.
- `app/models/connection.py` is the shared ADME contract; backend auth and health services should consume `ADMEConnection`, `ServiceHealthResult`, and `OSDU_SERVICES` without redefining them.
- Judson's backend-facing API for issue #2 is intentionally thin: `app/services/auth.py:get_token(connection)` and `app/services/health.py:check_all(connection, token)`.
- Health validation should preserve `OSDU_SERVICES` order, classify non-2xx HTTP responses as `unhealthy`, and classify transport failures like timeouts as `error`.
- Health probes must send both `Authorization` and `data-partition-id`, and tests should keep `tests/conftest.py` fixtures aligned with that required input.
- EDS belongs in the issue #2 service matrix and should use the explicit readiness health endpoint (`/api/eds/v1/health/readiness_check`) with `GET`, not the business `retrievalInstructions` API.
- Indexer health validation must use the non-mutating readiness endpoint (`/api/indexer/v2/readiness_check`); `reindex` is an operational action, not a safe probe contract.

## 2026-04-24 Issue #2 Contract Corrections (Revision Batch)
- Fixed Indexer probe contract: removed mutating GET /api/indexer/v2/reindex, replaced with read-only GET /api/indexer/v2/readiness_check
- Finalized EDS probe: confirmed GET /api/eds/v1/health/readiness_check (dedicated health endpoint), rejected POST /api/eds/v1/retrievalInstructions (business API, false negatives)
- Established health status semantics: healthy (2xx), unhealthy (non-2xx with code/detail), error (transport/timeout, no status_code)
- No redirect following (redirects hide auth/gateway misconfig)
- Deterministic result ordering per OSDU_SERVICES list for UI/test matrix rendering
- All tests updated and re-run against corrected contracts
- Issue #2 updated with real current status
- Ready for Judson's UI integration
