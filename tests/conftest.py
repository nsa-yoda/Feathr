"""Test command options shared by the repository's quality targets."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pass-with-no-tests",
        action="store_true",
        help="return success when the selected test directory has no tests",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if (
        session.config.getoption("--pass-with-no-tests")
        and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED
    ):
        session.exitstatus = pytest.ExitCode.OK
