"""Smoke tests for the ADME control plane app module."""

from app import __version__


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"
