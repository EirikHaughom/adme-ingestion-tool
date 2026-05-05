---
name: "streamlit-page-testing"
description: "Use a recorder double to unit test Streamlit page modules without launching Streamlit."
domain: "testing"
confidence: "high"
source: "earned"
---

## Context
Use this skill when testing Streamlit modules in this repo, especially page renderers under `app\` and `app\pages\`. It applies when the code mostly calls `streamlit` functions directly and the important behavior is which UI APIs were called with which values.

## Patterns
- If Streamlit is not installed in the test environment, insert `StreamlitRecorder` into `sys.modules["streamlit"]` before importing the page module.
- Replace the module-local `st` import with `tests.support.streamlit_recorder.StreamlitRecorder` using `monkeypatch`.
- Keep one behavior per test: page config, title, and body copy should each have their own assertion.
- Keep reusable connection fixtures in `tests\conftest.py` so welcome/settings tests share the same auth payloads and service list.
- Use a single canonical service list for ADME health validation to avoid drift across UI and backend tests.
- Assert conditional field presence and absence when auth method or workflow state changes.
- For secret-bearing inputs, assert the widget uses `type="password"` and that the non-secret auth path does not render the field at all.
- Guard the issue or contract field set directly in tests so UI changes do not quietly add extra required inputs.
- For non-secret configuration fields that operators could confuse with credentials (for example token scope), assert the in-page help or caption says it is not a token or secret and explains when to override it. README-only safety wording is not enough.

## Examples
- `tests\support\streamlit_recorder.py`
- `tests\test_main.py`
- `tests\conftest.py`

## Anti-Patterns
- Launching a real Streamlit runtime just to verify static page calls.
- Writing one giant assertion that tries to prove the entire page in a single test.
- Duplicating the ADME service list across many tests.
- Treating secret-bearing fields like normal text inputs in assertions or logs.
