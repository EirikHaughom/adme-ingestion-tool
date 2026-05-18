"""Sanity tests for the vendored OSDU open-test-data assets.

These confirm the v1 vendor commit shipped what `app/data/osdu/rc--3.0.0/`
and `app/vendor/azure_tno_loader/` are supposed to ship — and that no
runtime-substitution tokens leaked through that the loader would otherwise
need to expand. The loader itself does not exist yet (it lands in a later
branch); these tests only guard the inputs to that future work.

The reference-data manifests and schemas are OSDU-generic (lookup tables,
schema definitions) and live under `app/data/osdu/`. Dataset-specific
artifacts (master-data, work-products) belong under `app/data/datasets/`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "app" / "vendor" / "azure_tno_loader"
OSDU_DIR = REPO_ROOT / "app" / "data" / "osdu" / "rc--3.0.0"
REF_DATA_DIR = OSDU_DIR / "reference-data"
SCHEMAS_DIR = OSDU_DIR / "schemas"
DATASETS_DIR = REPO_ROOT / "app" / "data" / "datasets"


def test_csv_to_json_script_vendored() -> None:
    path = VENDOR_DIR / "csv_to_json.py"
    assert path.exists(), f"missing vendored script: {path}"
    assert path.stat().st_size > 0, f"vendored script is empty: {path}"


def test_csv_to_json_wrapper_vendored() -> None:
    path = VENDOR_DIR / "csv_to_json_wrapper.py"
    assert path.exists(), f"missing vendored wrapper: {path}"
    assert path.stat().st_size > 0, f"vendored wrapper is empty: {path}"


def test_vendor_package_importable() -> None:
    # __init__.py must exist so `app.vendor.azure_tno_loader` is a package.
    assert (VENDOR_DIR / "__init__.py").exists()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.vendor.azure_tno_loader import csv_to_json_wrapper; "
                "print(csv_to_json_wrapper.create_manifest_from_csv.__name__)"
            ),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.strip() == "create_manifest_from_csv"


def test_reference_data_directory_populated() -> None:
    assert REF_DATA_DIR.is_dir(), f"missing dir: {REF_DATA_DIR}"
    json_files = list(REF_DATA_DIR.glob("*.json"))
    assert len(json_files) > 0, (
        f"reference-data dir has no JSON manifests: {REF_DATA_DIR}"
    )


def test_schemas_directory_populated() -> None:
    assert SCHEMAS_DIR.is_dir(), f"missing dir: {SCHEMAS_DIR}"
    json_files = list(SCHEMAS_DIR.rglob("*.json"))
    assert len(json_files) > 0, f"schemas dir has no JSON files: {SCHEMAS_DIR}"


@pytest.mark.parametrize(
    "token",
    [
        "<namespace>",
        "{{viewers}}",
        "{{owners}}",
        "{{legal-tag-name}}",
        "{{legal-tag}}",
    ],
)
def test_reference_data_has_no_substitution_tokens(token: str) -> None:
    """Pre-conversion claim: any literal substitution tokens upstream uses
    should already be resolved (or absent) in the vendored snapshot. If a
    future refresh re-introduces them, this test fails and the loader needs
    to grow a substitution pass before submission."""
    offenders: list[str] = []
    for path in REF_DATA_DIR.rglob("*.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        if token in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"token {token!r} still present in vendored reference-data files: "
        f"{offenders[:5]}"
    )


def test_notice_files_exist_with_required_fields() -> None:
    azure_notice = VENDOR_DIR / "NOTICE.md"
    osdu_notice = OSDU_DIR / "NOTICE.md"
    assert azure_notice.exists(), f"missing: {azure_notice}"
    assert osdu_notice.exists(), f"missing: {osdu_notice}"

    azure_text = azure_notice.read_text(encoding="utf-8")
    for field in (
        "Apache",
        "github.com/Azure/osdu-data-load-tno",
        "2026-05-12",
        "csv_to_json.py",
        "csv_to_json_wrapper.py",
    ):
        assert field in azure_text, (
            f"NOTICE.md missing required field {field!r}: {azure_notice}"
        )

    osdu_text = osdu_notice.read_text(encoding="utf-8")
    for field in (
        "Apache",
        "community.opengroup.org/osdu/data/open-test-data",
        "rc--3.0.0",
        "2026-05-12",
    ):
        assert field in osdu_text, (
            f"NOTICE.md missing required field {field!r}: {osdu_notice}"
        )


def test_readme_documents_token_conversion() -> None:
    readme = OSDU_DIR / "README.md"
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    # README must state what token conversions were applied so a future
    # operator refreshing the snapshot knows what to expect.
    assert "<namespace>" in text or "no-op" in text.lower() or "zero" in text.lower()
