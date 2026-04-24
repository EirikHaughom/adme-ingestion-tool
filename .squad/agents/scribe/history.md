# Project Context

- **Owner:** Eirik Haughom
- **Project:** Streamlit control plane app for Azure Data Manager for Energy (ADME)
- **Stack:** Python, Streamlit, Azure, ADME/OSDU APIs
- **Created:** 2026-04-24

## Learnings

- Scribe owns decisions.md, decisions/inbox, orchestration logs, and session logs for the ADME Streamlit squad.
- Initial roster: Satya, Judson, Kevin, Scott, Charlie, Ralph, and Scribe.

## 2026-04-24 First Session
- Scribe role established for decision documentation and team communication
- Processed 3 inbox items from agent Satya (issue #1 scaffolding)
- Created decisions.md as central decision registry
- Created orchestration and session logs

## 2026-04-24 Issue #2 Consolidation (Design & Test)
- Merged 2 design/test inbox decisions (Satya architecture, Charlie review gate)
- Satya approved connection layer architecture, committed app/models/connection.py
- Charlie defined acceptance criteria and created test scaffolding
- Identified review risks: auth switching, unauthorized services, timeouts, partial failures
- Created orchestration logs for Satya and Charlie (issue #2)
- Documented review gate blocking criteria (auth coverage, M25 health matrices, error handling, product sign-off)

## 2026-04-24 Kevin Issue #2 Revision Batch
- Processed 6 inbox items (3 Kevin contract corrections, 3 others)
- Merged Kevin decisions: Indexer probe fix, EDS probe finalization, health status semantics
- Created Kevin orchestration log (issue #2 revision batch)
- Created session log for contract-fix batch
- Updated kevin/history.md with probe contract details
