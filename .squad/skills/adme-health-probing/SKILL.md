---
name: adme-health-probing
description: Validate ADME/OSDU connectivity with explicit per-service probe semantics
domain: integration, error-handling
confidence: high
source: earned (issue #2 backend implementation)
---

## Context

Use this pattern when validating an ADME connection against multiple OSDU services and the UI needs deterministic, debuggable results.

## Patterns

- Treat `app/models/connection.py` as the source of truth for `OSDU_SERVICES` and shared result models.
- Probe services concurrently with a short timeout so one slow dependency does not block the whole report.
- Send both `Authorization: Bearer <token>` and `data-partition-id` on every probe.
- Use the canonical Search probe body `{"kind": "*:*:*:*", "limit": 1}` and `POST` for Search while using `GET` for the other lightweight probes.
- For EDS specifically, prefer the dedicated readiness endpoint over the business retrieval API so validation measures service health rather than payload correctness.
- Classify 2xx responses as `healthy`, non-2xx responses as `unhealthy`, and transport failures as `error`.
- Disable redirects so gateway or auth misroutes stay visible instead of looking like successful checks.
- Preserve contract order in the returned results so UI tables and tests stay deterministic.

## Examples

- `app/services/health.py` implements concurrent probing with explicit status mapping.
- `tests/test_health.py` shows how to validate headers, Search POST behavior, redirect handling, and status semantics.

## Anti-Patterns

- Rebuilding the service list outside `OSDU_SERVICES`
- Following redirects during validation
- Collapsing HTTP failures and network failures into one vague status
- Returning probe results in completion order instead of contract order
