# ADME Ingestion Tool

Operator control plane for **Azure Data Manager for Energy (ADME)**, built with Python and Streamlit.

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

## Project Structure

```
app/              # Streamlit application
  main.py         # Entry point
  pages/          # Multipage navigation
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