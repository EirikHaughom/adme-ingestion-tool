# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Satya owns scope, architecture decisions, and reviewer gating for the ADME control plane.
- The product is an operator-facing Streamlit app for managing ADME workflows and platform operations.
- 2026-04-24: Established project scaffolding — flat `app/` layout, `pyproject.toml` as config hub, latest stable deps (Streamlit 1.56+, Python ≥3.11, ruff 0.15+, pytest 9.0+).
- Key file paths: `app/main.py` (entry point), `pyproject.toml` (deps + tool config), `.streamlit/config.toml` (UI theme), `tests/` (test suite).
- Ownership: Judson=UI, Kevin=backend services, Scott=infra/CI, Charlie=tests.
- Design choice: flat `app/` over `src/` layout because Streamlit apps run with `streamlit run app/main.py`, not as installed packages.
- Streamlit theme uses Microsoft Fluent colors (#0078d4 primary) to match ADME branding.

## 2026-04-24 Scribe Consolidation
- Decision to use GitHub Issues for all work tracking (user directive)
- Decision to always update GitHub issues with real status (user directive)
- Streamlit architecture decision documented and archived
- Team ownership split documented: Judson=UI, Kevin=backend, Scott=infra, Charlie=tests
