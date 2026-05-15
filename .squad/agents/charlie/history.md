# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Current Role Summary

Charlie (Tester) owns test strategy, acceptance criteria, and quality gates for the control plane. Highest-risk areas: auth, operator actions, backend integration failures, regression coverage.

**Key learnings from prior work:**
- Reusable Streamlit test pattern: monkeypatch st import with 	ests.support.streamlit_recorder.StreamlitRecorder
- Health probe selection critical: avoid mutating endpoints, use read-only or dedicated endpoints
- Team sign-off protocol: lead review, named reviser for issues, comprehensive re-review after fixes
- Acceptance criteria defined upfront enable fast iteration and clear gate definition
- Operator UX requires clear messaging for browser flows, tenant/scope, error recovery
- Auth testing must cover mode switching, secret masking, per-service health, pending-flow regression

**Archived work:** Issues #2–#7 (auth architecture, browser login, callback fix, tenant auth, redirect). Issue #8 (MSAL integration) and manual token scope completed 2026-05-05. See history-archive.md for full details.

## 2026-05-05: Persistent Storage Verification Plan (Current)

**Status:** PLANNING COMPLETE, SYNTHESIZED WITH TEAM

**Acceptance criteria A1–A8 locked and ready for implementation review:**

- **A1:** Storage configuration & mode switching (SQLite default .adme_dev.db, PostgreSQL via DATABASE_URL, unambiguous mode, clear startup log)
- **A2:** Session ↔ persistent storage sync (connection persists, auth NOT persisted, health time-scoped, secrets NEVER)
- **A3:** Migration safety & backward compatibility (version-controlled schema, fresh-install initialization, identical Postgres/SQLite schemas, pre-persistent-storage migration)
- **A4:** Secret handling & sensitive data (no logging of secrets, masked UI, env-only DATABASE_URL, .gitignore enforcement)
- **A5:** Failure states & recovery (connection failure graceful, corrupt DB detected, transaction rollback, clear state handling)
- **A6:** Streamlit reruns & concurrent access (no data race, no per-interaction re-read, session/storage separation clear in code)
- **A7:** CI/CD feasibility (tests without external Postgres, migrations tested in CI, optional Postgres developer path, no environment branches)
- **A8:** Data integrity & constraints (NOT NULL/UNIQUE where needed, stable primary keys, UTC timestamps)

**Test phases ready to execute:**
1. **Unit tests (Phase 1):** Schema/migration, connection persistence, health results, secret handling, failure recovery, concurrent access
2. **Integration tests (Phase 2):** Settings → DB → Welcome flow, auth method switching, health persistence, backward compatibility
3. **System/acceptance tests (Phase 3):** Full pytest with coverage, ruff, mypy, manual dev and Postgres paths
4. **Operational tests (Phase 4):** Data survives restart, Postgres path documented, no secret leakage

**Critical review gates defined:**
- [ ] SQLAlchemy ORM abstraction only (no raw SQL)
- [ ] grep -r "client_secret" app/storage/ returns nothing
- [ ] Schema audit: correct PKs, constraints, no orphaned data
- [ ] Transaction audit: all writes atomic
- [ ] CI/CD audit: no external service deps
- [ ] Error handling audit: all DB errors caught with user-friendly messages

**Known risks & mitigations:**
1. Streamlit session ↔ DB sync timing → lock mechanism or read-once-per-session
2. SQLite vs Postgres behavior → SQLAlchemy + matrix tests
3. Client secret leakage → validator wrapping, log filtering, fresh review
4. Operator confusion (DB vs session) → clear UI labels, integration test proof

**Role confirmation:**
- Satya: review all phases, arbitrate conflicts
- Kevin: Phase 1 implementation (storage layer)
- Judson: Phase 2 implementation (UI persistence)
- Scott: Phase 3 implementation (deployment, secrets plumbing)
- Charlie: Phase 4 gating (acceptance criteria verification)

**Ready to gate implementation:** All A1–A8 criteria and test suites committed to decisions.md. Team sign-off required before coding begins.

## 2026-05-05T20:00:00.287+02:00: Persistent Storage Verification Implementation

- Added storage bridge tests that prove persisted connection and health state can
  hydrate Settings and Welcome flows without operator re-entry of non-secret
  fields, while keeping client secrets out of storage-bound calls.
- Added concrete `app.storage` contract tests for SQLite default/redaction,
  migration initialization, non-secret profile round-trip, active profile
  restart survival, health result timestamp retrieval, and rollback under
  injected health-result write failure.
- Concrete `app.storage` appeared during the run, so the acceptance tests were
  adapted to its SQLAlchemy repository classes and UI bridge.
- Validation: `python -m pytest --no-cov -q` passed with 101 passed and 1
  skipped; configured `python -m pytest`, Ruff, and mypy also passed.

## 2026-05-06T06:44:31.579Z: PR #9 Storage Alternative Comparison

**Verdict:** Local implementation satisfies all 8 acceptance criteria. PR #9 covers profile persistence only; misses PostgreSQL, migrations, health persistence, and failure-mode testing.

**Acceptance criteria verification:**
1. ✓ SQLite default at `.adme/adme.db`
2. ✓ PostgreSQL via `DATABASE_URL`
3. ✓ No PGlite
4. ✓ SQLAlchemy/Alembic boundary under `app/storage`
5. ✓ No persisted secrets
6. ✓ SQLite auto-migrates; PostgreSQL revision check
7. ✓ Profile/health hydration in Streamlit pages
8. ✓ Test coverage for migration, round-trip, secret rejection, health atomicity

**PR #9 gaps:** Profile persistence only; missing PostgreSQL production validation, migration verification, health persistence and atomicity, and failure-mode testing.

**Recommendation:** STICK WITH LOCAL; close PR #9 as superseded. All test gates passing (101 passed, 1 skipped).

## 2026-05-15T12:27:55.007+02:00: PR #9 Test Hardening Port

- Ported the useful PR #9 hardening pattern as a root autouse `DATABASE_URL` isolation fixture so tests default to a per-test SQLite database instead of any operator `.adme\adme.db` or home/user store.
- Strengthened storage repository coverage with a raw SQLite file bytes assertion proving the rejected service-principal `client_secret` value is absent after a persistence attempt; kept the existing bridge-level raw bytes check for stripped session-only values.
- Kept the local SQLAlchemy/Alembic storage boundary; did not port PR #9 sqlite3 settings store, ADME_SETTINGS_DB, keyring, or connection_state coupling.
- Validation: focused storage tests passed; full pytest passed; touched-file Ruff and full mypy passed. Full repository Ruff remains blocked by pre-existing issues outside this change.
