# ADME Ingestion Tool

Operator control plane for **Azure Data Manager for Energy (ADME)**, built with Python and Streamlit.

## Prerequisites

### Entra App Registration Redirect URI

If you plan to use **user impersonation** (app-returning sign-in through Entra), the Entra application registration that serves as the public client must include the redirect URI:

```
http://localhost:8501
```

**Why this matters:** Without this redirect URI, the browser-based OAuth sign-in will fail even if the code is correct. After the user authenticates in the browser, Entra will reject the callback to `http://localhost:8501` if it is not explicitly registered. This causes the authentication flow to hang or error at the final step.

To add this redirect URI:
1. Go to the Entra application registration (Azure Portal → Manage → App registrations).
2. Select the public-client application.
3. Go to **Authentication**.
4. Under **Redirect URIs**, add `http://localhost:8501`.
5. Save.

Service-principal authentication (using a client secret) does not require this step.

## Quick Start

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS / Linux

# Install dependencies
pip install -r requirements-dev.txt

# Run the app
streamlit run app/main.py

# Run tests
pytest
```

## Walkthroughs

- [TNO end-to-end: ingest a single file](docs/walkthroughs/tno-end-to-end.md) — upload → build manifest → submit → verify in Search.

## Operator Flow

1. Open the welcome page to see whether the current Streamlit session already has an ADME connection.
2. Go to **Instance Configuration** to enter the ADME endpoint, tenant, client, data partition, auth method, and token scope.
3. Use **Test Connection** to authenticate and probe each configured OSDU service before starting work. For user impersonation, you will sign in through Entra in your browser; the session will return automatically to Streamlit when complete.

### Instance Configuration: Token Scope

The **Token scope** field specifies the OAuth resource scope requested when acquiring ADME access tokens. This is a **configuration setting, not a secret**—it contains no tokens, credentials, or authorization codes.

**Default:** `https://energy.azure.com/.default`

**When to override:** You should only change this value if your organization's Entra app registration or ADME deployment requires a different OAuth resource scope. In most cases, the default is correct. Consult your Azure administrator or ADME team if you are unsure whether a custom scope is needed.

**Security note:** This field is not sensitive material and should never contain tokens, client secrets, access codes, or other credential data. If you see instructions asking you to paste a token or secret into this field, that is a mistake—contact your administrator instead.

## Project Structure

```
app/              # Streamlit application
  main.py         # Welcome page + grouped Setup / Operate navigation
  pages/          # Multipage navigation
    1_⚙️_Instance_Configuration.py  # Setup: ADME connection form + health validation
    2_🔑_Entitlements.py            # Setup: entitlements smoke test
    3_🏷️_Legal_Tags.py             # Setup: legal-tag CRUD
    4_📥_Ingest.py                  # Ingest: landing page / method chooser
    5_📄_Manifest.py                # Ingest: manifest ingestion + workflow polling
    6_📂_File.py                    # Ingest: single-file upload via OSDU File Service v2
    7_🔍_Search.py                  # Operate: Search Service queries
  services/       # Auth and service-health integrations
tests/            # Test suite
.streamlit/       # Streamlit config
pyproject.toml    # Project metadata and tool config
```

## Stack

| Layer       | Technology              |
|-------------|-------------------------|
| UI          | Streamlit 1.56+         |
| Auth        | azure-identity          |
| HTTP        | requests                |
| Testing     | pytest, pytest-cov      |
| Linting     | ruff, mypy              |
| Runtime     | Python ≥ 3.11           |
