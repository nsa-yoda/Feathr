"""Security boundary regression coverage for Feature 017."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from event_platform.api.middleware.body_limit import BodyLimitMiddleware
from event_platform.core.logging import JsonLogFormatter
from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.storage.mongo import EventQuery

pytestmark = pytest.mark.unit


def test_declared_oversized_body_is_rejected_before_route_parsing() -> None:
    settings = ServiceSettings(env="test", request_body_max_bytes=1_024)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/events",
            content=b"{" + b"x" * 1_024 + b"}",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == "request_body_too_large"
    assert "x" * 500 not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-operation-id"]


@pytest.mark.asyncio
async def test_streamed_oversized_body_is_rejected_without_content_length() -> None:
    messages = iter(
        (
            {"type": "http.request", "body": b"a" * 600, "more_body": True},
            {"type": "http.request", "body": b"b" * 500, "more_body": False},
        )
    )
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return next(messages)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    handler_invoked = False

    async def consumer(scope: dict[str, object], receive, send) -> None:
        nonlocal handler_invoked
        await receive()
        await receive()
        handler_invoked = True

    middleware = BodyLimitMiddleware(consumer, max_bytes=1_024)
    await middleware(
        {
            "type": "http",
            "path": "/events",
            "headers": [],
            "state": {},
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 413
    body = sent[1]["body"]
    assert isinstance(body, bytes)
    assert json.loads(body)["error_code"] == "request_body_too_large"
    assert handler_invoked is False


def test_exact_origin_cors_and_security_headers() -> None:
    settings = ServiceSettings(env="test", cors_allowed_origin="https://ui.example.test")
    with TestClient(create_app(settings)) as client:
        allowed = client.options(
            "/events",
            headers={
                "Origin": "https://ui.example.test",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied = client.options(
            "/events",
            headers={
                "Origin": "https://evil.example.test",
                "Access-Control-Request-Method": "POST",
            },
        )
        normal = client.get("/health/live", headers={"Origin": "https://ui.example.test"})

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://ui.example.test"
    assert allowed.headers["access-control-allow-methods"] == "GET, POST, OPTIONS"
    assert "Content-Type" in allowed.headers["access-control-allow-headers"]
    assert "Idempotency-Key" in allowed.headers["access-control-allow-headers"]
    assert "access-control-allow-credentials" not in allowed.headers
    assert "access-control-allow-origin" not in denied.headers
    assert normal.headers["x-frame-options"] == "DENY"
    assert normal.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in normal.headers["content-security-policy"]


def test_security_settings_reject_wildcard_and_bound_timeout() -> None:
    with pytest.raises(ValueError):
        ServiceSettings(cors_allowed_origin="*")
    with pytest.raises(ValueError):
        ServiceSettings(cors_allowed_origin="https://ui.example.test/path")
    with pytest.raises(ValueError):
        ServiceSettings(cors_allowed_origin="https://ui.example.test:bad")
    with pytest.raises(ValueError):
        ServiceSettings(cors_allowed_origin="https://ui.example.test/")
    with pytest.raises(ValueError):
        ServiceSettings(cors_allowed_origin="https://user:password@ui.example.test")
    assert ServiceSettings(env="test").cors_allowed_origin is None
    with pytest.raises(ValueError):
        ServiceSettings(dependency_timeout_seconds=0.01)


def test_production_requires_non_placeholder_operator_token() -> None:
    with pytest.raises(ValueError, match="production_api_token"):
        ServiceSettings(
            env="production",
            mongo_url="mongodb://mongo:27017",
            cursor_signing_key="c" * 32,
            production_api_token="changeme",
        )


@pytest.mark.asyncio
async def test_production_protected_routes_require_bearer_token() -> None:
    from event_platform.api.middleware.production_auth import ProductionAuthMiddleware

    class State:
        settings = ServiceSettings(
            env="production",
            mongo_url="mongodb://mongo:27017",
            cursor_signing_key="c" * 32,
            production_api_token="t" * 32,
        )

    class App:
        state = State()

    sent: list[dict[str, object]] = []

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "path": "/health/components",
        "headers": [],
        "state": {},
        "app": App(),
    }
    await ProductionAuthMiddleware(downstream)(scope, lambda: None, send)
    assert sent[0]["status"] == 401


def test_query_and_search_input_abuse_returns_safe_validation() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        control = client.get("/events/search", params={"q": "unsafe\nterm"})
        long_cursor = client.get("/events/search", params={"q": "term", "cursor": "x" * 513})
        long_range = client.get(
            "/events",
            params={"start": "2020-01-01T00:00:00Z", "end": "2022-01-02T00:00:00Z"},
        )

    assert control.status_code == 422
    assert long_cursor.status_code == 422
    assert long_range.status_code == 422
    assert "unsafe" not in control.text
    assert "x" * 100 not in long_cursor.text


def test_query_string_limit_and_canonical_filters_reject_abuse() -> None:
    with TestClient(create_app(ServiceSettings(env="test", request_query_max_bytes=256))) as client:
        response = client.get("/health/live?" + "x" * 257)

    assert response.status_code == 414
    assert response.json()["error_code"] == "request_query_too_large"
    assert response.headers["x-operation-id"]
    with pytest.raises(ValueError):
        EventQuery(event_type="unsafe\nterm")
    with pytest.raises(ValueError):
        EventQuery(user_id="unsafe\x7fvalue")


def test_metadata_abuse_is_rejected_at_http_boundary_before_queue_admission() -> None:
    sent = 0

    class RecordingQueue:
        async def send(self, *args: object, **kwargs: object) -> None:
            nonlocal sent
            sent += 1

    app = create_app(ServiceSettings(env="test"))
    with TestClient(app) as client:
        app.state.queue = RecordingQueue()
        payload = {
            "event_type": "pageview",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "user-1",
            "source_url": "https://example.test/page",
            "metadata": {"a": {"b": {"c": {"d": {"e": {"f": "SENTINEL"}}}}}},
        }
        response = client.post("/events", json=payload)

    assert response.status_code == 422
    assert "SENTINEL" not in response.text
    assert sent == 0


def test_container_definitions_declare_non_root_runtime() -> None:
    root = Path(__file__).parents[2]
    app_dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    ui_dockerfile = (root / "frontend/Dockerfile").read_text(encoding="utf-8")

    assert "USER 10001:10001" in app_dockerfile
    assert "USER 101" in ui_dockerfile


def test_dependency_url_credentials_are_redacted_from_structured_messages() -> None:
    formatter = JsonLogFormatter()
    record = logging.makeLogRecord(
        {"msg": "redis://user:secret@redis.internal:6379/0 mongodb://admin:pw@mongo.internal"}
    )

    rendered = formatter.format(record)

    assert "secret" not in rendered
    assert "pw@" not in rendered
    assert "redis.internal:6379" in rendered
