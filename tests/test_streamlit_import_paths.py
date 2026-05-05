"""Regression tests for Streamlit script import-path handling."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
MAIN_PATH = APP_ROOT / "main.py"
SETTINGS_PAGE_PATH = APP_ROOT / "pages" / "1_⚙️_Settings.py"


def _run_streamlit_like_import(script_path: Path) -> subprocess.CompletedProcess[str]:
    code = textwrap.dedent(
        f"""
        import importlib.util
        import sys
        import types
        from pathlib import Path

        project_root = Path({str(PROJECT_ROOT)!r})
        script_path = Path({str(script_path)!r})
        sys.modules["streamlit"] = types.ModuleType("streamlit")
        sys.path = [str(script_path.parent)] + [
            path
            for path in sys.path
            if Path(path or ".").resolve()
            not in {{project_root.resolve(), (project_root / "app").resolve()}}
        ]
        spec = importlib.util.spec_from_file_location(
            "streamlit_script_under_test",
            script_path,
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        """
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT,
        text=True,
    )


def test_main_imports_with_only_app_directory_on_sys_path() -> None:
    result = _run_streamlit_like_import(MAIN_PATH)

    assert result.returncode == 0, result.stderr


def test_settings_page_imports_with_only_pages_directory_on_sys_path() -> None:
    result = _run_streamlit_like_import(SETTINGS_PAGE_PATH)

    assert result.returncode == 0, result.stderr
