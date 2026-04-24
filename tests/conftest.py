"""Shared pytest fixtures for ADME control plane tests."""

import pytest


@pytest.fixture
def app_title() -> str:
    """Return the expected application title."""
    return "ADME Control Plane"
