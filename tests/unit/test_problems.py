"""The foundation uses one safe HTTP problem contract."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from event_platform.main import create_app

pytestmark = pytest.mark.unit


def assert_problem(response: Response, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "error_code",
        "request_id",
    }
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["error_code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    UUID(str(body["request_id"]))
    return body


def test_unknown_route_uses_problem_shape_without_query_reflection() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/missing?secret=SENTINEL_PRIVATE_QUERY")

    body = assert_problem(response, 404, "route_not_found")
    assert body["title"] == "Not Found"
    assert body["instance"] == "/missing"
    assert "SENTINEL_PRIVATE_QUERY" not in str(body)


def test_method_not_allowed_preserves_allow_header() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/health/live")

    body = assert_problem(response, 405, "http_405")
    assert body["title"] == "Method Not Allowed"
    assert "GET" in response.headers["allow"]


def test_validation_error_uses_safe_problem_shape() -> None:
    app = create_app()

    @app.get("/requires-int")
    async def requires_int(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/requires-int?value=SENTINEL_BAD_VALUE")

    body = assert_problem(response, 422, "request_validation_failed")
    assert body["title"] == "Unprocessable Content"
    assert body["instance"] == "/requires-int"
    assert "SENTINEL_BAD_VALUE" not in str(body)


def test_unexpected_error_is_sanitized_and_keeps_request_id() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("SENTINEL_PRIVATE_FAILURE")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    body = assert_problem(response, 500, "internal_error")
    assert body["title"] == "Internal Server Error"
    assert "SENTINEL_PRIVATE_FAILURE" not in str(body)
    assert "Traceback" not in str(body)


def test_openapi_declares_problem_media_type_for_health() -> None:
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()

    responses = document["paths"]["/health/live"]["get"]["responses"]
    for status in ("404", "405", "422", "500"):
        assert "application/problem+json" in responses[status]["content"]
