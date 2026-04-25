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

## 2026-04-24 Issue #2 Final Completion Batch
- Merged 1 final decision item (charlie-issue-2-final-approval.md)
- Created orchestration logs for Judson (implementation) and Charlie (final review/approval)
- Kevin implementation batch orchestration already logged separately
- Created session log for issue #2 final completion
- Updated judson/history.md with welcome/settings pages implementation
- Updated kevin/history.md with auth/health services implementation
- Updated charlie/history.md with final approval decision
- Issue #2 fully APPROVED and ready to close

## 2026-04-24 Issue #3 Final Completion Batch
- Merged 1 decision item (judson-streamlit-import-fix.md)
- Created orchestration logs for Judson (implementation) and Charlie (final review/approval)
- Created session log for issue #3 final completion
- Updated judson/history.md with import-path fix details
- Updated charlie/history.md with final approval decision
- Updated identity/now.md: issue #3 approved/closed, no active issues

## 2026-04-24 Issue #4 Full Completion Batch
- Merged 5 decision items: Satya design, Charlie planning & final review, Kevin implementation, Judson UX, user directive
- Created orchestration logs for Satya (design), Charlie (planning), Kevin (implementation), Judson (implementation), Charlie (final review)
- Created session log for issue #4 full completion batch
- Updated satya/history.md with design approval
- Updated kevin/history.md with backend implementation details
- Updated judson/history.md with UI updates and documentation
- Updated charlie/history.md with test gates and final approval
- Issue #4 fully APPROVED and ready to close

## 2026-04-25 Issue #5 Full Completion Batch
- Merged 3 decision items: Satya design (public client fix), Charlie planning (test gates), Kevin implementation (backend changes)
- Created orchestration logs for Satya (design/root cause), Charlie (planning & final review), Kevin (implementation)
- Created session log for issue #5 full completion batch
- Updated satya/history.md with callback fix design
- Updated kevin/history.md with backend implementation, public client ID constant, test coverage
- Updated charlie/history.md with planning gates and final approval
- Issue #5 fully APPROVED and ready to close
- All 5 sprint issues (#1-#5) now complete and approved

## 2026-04-25 Issue #6 Full Completion Batch
- Merged 3 decision items: Satya design (tenant-compatible fix), Charlie planning (acceptance criteria & gates), Kevin implementation (backend changes)
- Root cause: Azure CLI public client ID is blocked in some enterprise tenants (IPS-Energy); solution: use customer's app registration + hardcoded ADME scope
- Created orchestration logs for Satya (design), Charlie (planning), Kevin (implementation), Charlie (final review)
- Created session log for issue #6 full completion batch
- Updated satya/history.md with tenant-compatible auth design
- Updated kevin/history.md with backend implementation, scope hardcoding, test coverage
- Updated charlie/history.md with planning gates and final approval
- Issue #6 fully APPROVED and ready to close
- All 6 sprint issues (#1-#6) now complete and approved
- decisions.md grew from 14.5KB to 18.2KB (under 20KB hard gate)
- Inbox cleared (0 items); all 6 issues fully consolidated

## 2026-04-25 Issue #7 Full Completion Batch
- Merged 3 decision items: Satya design (redirect behavior), Charlie planning (acceptance criteria & gates), Kevin implementation (explicit redirect_uri)
- Root cause: InteractiveBrowserCredential requires SDK's own localhost:8400 listener for OAuth code capture; cannot redirect to Streamlit; users didn't know to switch back
- Solution: (1) Update Settings guidance to explain new tab opens for sign-in, user should return to Streamlit after closing it; (2) Explicitly pass redirect_uri="http://localhost:8400" to credential for determinism
- Created orchestration logs for Satya (design), Charlie (planning), Kevin (backend), Judson (UI), Charlie (final review)
- Created session log for issue #7 full completion batch
- Updated satya/history.md with auth redirect design approval
- Updated kevin/history.md with backend implementation, INTERACTIVE_BROWSER_REDIRECT_URI constant, test coverage
- Updated judson/history.md with Settings guidance text updates
- Updated charlie/history.md with planning gates and final approval (5/5 reviewer gates APPROVED)
- Issue #7 fully APPROVED and ready to close
- All 7 sprint issues (#1-#7) now complete and approved
- decisions.md grew from 18.2KB to 19.8KB (under 20KB hard gate)
- Inbox cleared (0 items); all 7 issues fully consolidated

