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
    4_📥_Ingestion.py               # Operate: manifest ingestion + workflow polling
  services/       # Auth and service-health integrations
tests/            # Test suite
.streamlit/       # Streamlit config
pyproject.toml    # Project metadata and tool config
```

## Data Storage

The operator control plane stores connection profiles and service health results in a persistent database. The app uses SQLAlchemy with a single migration path for both local development and production deployments.

### Development: SQLite

By default, the app stores data in a local SQLite database at `.adme/adme.db`. This path is created automatically on first run; no additional setup is required. To use the default SQLite storage, simply run the app without setting the `DATABASE_URL` environment variable.

```bash
streamlit run app/main.py
```

SQLite migrations are applied automatically on app startup during development.

### Production & Shared Deployments: PostgreSQL 14+

**Single-operator local development uses SQLite.** For production deployments, multi-instance setups (containers, Streamlit Cloud, Azure Web Apps), or shared operator environments, you must use PostgreSQL 14 or later.

To use PostgreSQL, set the `DATABASE_URL` environment variable before starting the app:

```bash
export DATABASE_URL="postgresql+psycopg://user:password@host:5432/adme"
streamlit run app/main.py
```

**PostgreSQL URL format:** `postgresql+psycopg://[user[:password]@][host[:port]]/[database]`

Before the app starts, run any pending migrations explicitly:

```bash
alembic upgrade head
```

Migrations are **not** applied automatically in production. You are responsible for running `alembic upgrade head` before deploying a new app version.

#### Database credentials

Database passwords and credentials must never be stored in plaintext configuration files or committed to version control. Use Azure Key Vault, environment secrets, or your cloud platform's credential management system to provide `DATABASE_URL` at runtime. The app accepts `DATABASE_URL` as an environment variable only—it does not read credentials from split variables like `ADME_DB_HOST` or `ADME_DB_PASSWORD`.

### What is stored

The app persists non-sensitive configuration:
- **Connection profiles:** ADME endpoint URL, tenant ID, client ID, data partition, auth method, and OAuth scope.
- **Health results:** Summary and timestamp of the last successful service health check for each profile.
- **Service-principal client secrets:** Stored separately in the OS credential store/keyring, never in the application database.

**What is not stored:**
- Access tokens, refresh tokens, or token caches (session-only).
- MSAL authorization flows or OAuth authorization codes (session-only).
- User authentication material (session-only; cleared on sign-out).

### Limitations

**SQLite is not supported for:**
- Streamlit Cloud deployments (ephemeral filesystem)
- Azure Container Instances or Azure Web Apps (ephemeral filesystem)
- Multi-instance or horizontally scaled deployments (SQLite file-locking is not thread-safe across processes)

In these cases, you **must** use PostgreSQL.

## Stack

| Layer       | Technology              |
|-------------|-------------------------|
| UI          | Streamlit 1.56+         |
| Auth        | azure-identity          |
| HTTP        | requests                |
| Storage     | SQLAlchemy 2.x, Alembic |
| Testing     | pytest, pytest-cov      |
| Linting     | ruff, mypy              |
| Runtime     | Python ≥ 3.11           |
