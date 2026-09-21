"""Docker-free contract tests for the Feature 024 developer workflow."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
MAKEFILE = ROOT / "Makefile"
WORKFLOW = ROOT / ".github/workflows/ci.yml"
README = ROOT / "README.md"


def test_makefile_exposes_locked_quality_and_lifecycle_targets() -> None:
    text = MAKEFILE.read_text()
    for target in (
        "format-check",
        "lint",
        "typecheck",
        "test-unit",
        "test-integration",
        "test-failure",
        "all",
        "coverage",
        "compose-config",
        "compose-up",
        "compose-down",
        "compose-reset",
        "smoke",
        "postman",
        "rebuild-status",
        "rebuild-demo",
    ):
        assert f"{target}:" in text
    assert (
        "all: format-check lint typecheck dependency-check test-unit test-functional "
        "test-integration test-failure" in text
    )
    assert "uv run --locked" in text
    assert "compose-reset:" in text and "down -v" in text
    assert text.count("--env-file .env.example") >= 4
    assert "Guarded rebuild command" in text
    for target in (
        "format-check",
        "lint",
        "typecheck",
        "test-unit",
        "test-integration",
        "test-failure",
        "coverage",
        "rebuild-status",
        "rebuild-demo",
    ):
        recipe = text.split(f"{target}:", 1)[1].split("\n\n", 1)[0]
        assert "\n\t" in recipe


def test_ci_runs_independent_locked_static_tests_and_artifacts() -> None:
    text = WORKFLOW.read_text()
    assert "actions/checkout@v7" in text
    assert "actions/setup-python@v7" in text
    assert "actions/upload-artifact@v7.0.1" in text
    assert 'PYTHON_VERSION: "3.14"' in text
    assert 'UV_VERSION: "0.12.17"' in text
    assert "uv sync --locked" in text
    for command in (
        "make format-check",
        "make lint",
        "make typecheck",
        "make compose-config",
        "make test-unit",
        "make test-functional",
        "make test-failure",
        "make test-integration-required",
        "make test-e2e-required",
    ):
        assert command in text
    assert "cache-dependency-glob: uv.lock" in text
    assert "actions/upload-artifact@v7.0.1" in text
    assert "coverage/coverage.xml" in text
    assert "pull_request:" in text and "branches: [main]" in text
    assert "needs: quality" in text and "if: always()" in text
    assert "service:" in text and "make smoke" in text and "docker compose" in text


def test_readme_documents_reproducible_workflow_and_rebuild_cli() -> None:
    text = README.read_text()
    assert "make all" in text
    assert "make compose-up" in text
    assert "make compose-reset" in text
    assert "make rebuild-status" in text
    assert "make rebuild-demo" in text
    assert "make coverage" in text
    assert "make compose-config" in text and "make compose-down" in text
    assert "make smoke" in text and "make postman" in text
    assert "Python `>=3.12`" in text and "uv.lock" in text
    assert "application image" in text and "Python 3.14.7-slim" in text
