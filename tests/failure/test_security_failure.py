"""Security failure-path checks for redaction and bounded dependency setup."""

import logging

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app

pytestmark = pytest.mark.failure


def test_problem_and_logs_do_not_echo_sentinel_query(caplog: pytest.LogCaptureFixture) -> None:
    sentinel = "SENTINEL_SECRET_QUERY_VALUE"
    with caplog.at_level(logging.INFO):
        with TestClient(create_app(ServiceSettings(env="test"))) as client:
            response = client.get("/events/search", params={"q": sentinel + "\n"})

    assert response.status_code == 422
    assert sentinel not in response.text
    assert sentinel not in caplog.text
    assert "Traceback" not in caplog.text


def test_cors_never_allows_wildcard_origin() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        response = client.options(
            "/health/live",
            headers={
                "Origin": "https://evil.example.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers.get("access-control-allow-origin") is None
