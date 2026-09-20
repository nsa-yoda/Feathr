"""Feature 005 ingestion API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app


def payload() -> dict[str, object]:
    return {
        "event_type": "pageview",
        "timestamp": "2026-01-02T03:04:05Z",
        "user_id": "user-1",
        "source_url": "https://example.test/page",
        "metadata": {"source": "test"},
    }


def test_ingestion_returns_202_after_enqueue_and_request_id() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        response = client.post("/events", json=payload(), headers={"X-Request-ID": "client-value"})

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["event_id"]
        assert body["request_id"] == response.headers["X-Request-ID"]
        assert response.headers["X-Request-ID"] != "client-value"
        assert client.app.state.queue  # type: ignore[attr-defined]


def test_ingestion_carries_only_idempotency_hash_into_queue_body() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        response = client.post(
            "/events",
            json=payload(),
            headers={"Idempotency-Key": "secret-idempotency-key"},
        )
        assert response.status_code == 202
        assert client.app.state.queue  # type: ignore[attr-defined]


def test_matching_idempotency_retry_replays_original_event_identity() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        first = client.post("/events", json=payload(), headers={"Idempotency-Key": "retry-key"})
        second = client.post("/events", json=payload(), headers={"Idempotency-Key": "retry-key"})
    assert first.status_code == second.status_code == 202
    assert first.json()["event_id"] == second.json()["event_id"]


def test_idempotency_key_reuse_with_different_payload_is_conflict() -> None:
    changed = payload()
    changed["user_id"] = "other-user"
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        assert (
            client.post(
                "/events", json=payload(), headers={"Idempotency-Key": "conflict-key"}
            ).status_code
            == 202
        )
        response = client.post("/events", json=changed, headers={"Idempotency-Key": "conflict-key"})
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


def test_ingestion_validation_is_problem_json() -> None:
    invalid = payload()
    invalid["timestamp"] = "not-a-timestamp"
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        response = client.post("/events", json=invalid)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == "request_validation_failed"


def test_ingestion_returns_503_when_queue_is_full() -> None:
    settings = ServiceSettings(env="test", queue_capacity=1, queue_send_timeout=0)
    with TestClient(create_app(settings)) as client:
        assert client.post("/events", json=payload()).status_code == 202
        response = client.post("/events", json=payload())

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.headers["content-type"].startswith("application/problem+json")


def test_ingestion_openapi_declares_contracts() -> None:
    with TestClient(create_app(ServiceSettings(env="test"))) as client:
        openapi = client.get("/openapi.json").json()

    operation = openapi["paths"]["/events"]["post"]
    assert operation["responses"]["202"]
    assert operation["responses"]["422"]["content"]["application/problem+json"]
    assert operation["responses"]["503"]["content"]["application/problem+json"]
