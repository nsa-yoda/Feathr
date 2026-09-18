"""The empty-suite pytest option preserves failures in selected tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _run_with_empty_suite_option(repo_root: Path, target: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(repo_root / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (source_path, str(repo_root), environment.get("PYTHONPATH")) if value
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(target),
            "--pass-with-no-tests",
            "-p",
            "tests.conftest",
        ],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_empty_suite_option_does_not_mask_test_failures(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    empty_suite = tmp_path / "empty"
    empty_suite.mkdir()
    failing_test = tmp_path / "test_failure.py"
    failing_test.write_text("def test_failure() -> None:\n    assert False\n", encoding="utf-8")

    empty_result = _run_with_empty_suite_option(repo_root, empty_suite)
    failing_result = _run_with_empty_suite_option(repo_root, failing_test)

    assert empty_result.returncode == 0, empty_result.stdout + empty_result.stderr
    assert failing_result.returncode != 0, failing_result.stdout + failing_result.stderr
