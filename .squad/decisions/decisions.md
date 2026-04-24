# Decisions

## Active Decisions

### 2026-04-24T14:20:35.493+02:00: Always use GitHub Issues for work tracking
**By:** Eirik Haughom (via Copilot)
**What:** Always use GitHub Issues for work tracking.
**Why:** User request — captured for team memory

### 2026-04-24T14:21:30.474+02:00: Always update GitHub issue with real status
**By:** Eirik Haughom (via Copilot)
**What:** Always update the relevant GitHub issue with the real status.
**Why:** User request — captured for team memory

### 2026-04-24T14:22:14.053+02:00: Streamlit environment architecture
**By:** Satya (Lead)
**What:** Established project structure using flat `app/` layout (not `src/`), `pyproject.toml` as single source of truth, and latest stable versions: Streamlit 1.56+, Python ≥3.11, ruff 0.15+, pytest 9.0+.
**Why:** Streamlit apps aren't libraries — flat layout keeps `streamlit run app/main.py` simple. Version floor of Python 3.11 balances modern features with broad compatibility. All tooling config lives in pyproject.toml to avoid config sprawl.

### Ownership split
- **Judson**: `app/main.py`, `app/pages/` — all Streamlit UI work
- **Kevin**: `app/services/` — ADME/OSDU API client backend
- **Scott**: `Dockerfile`, `.github/workflows/ci.yml`, Azure infra
- **Charlie**: `tests/` — test expansion, fixtures, CI integration
