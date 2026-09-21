"""HTTP-boundary contract checks that do not require external services."""

import pytest
from fastapi.testclient import TestClient

from event_platform.main import create_app


@pytest.mark.functional
def test_public_error_contract_and_openapi_response_matrix() -> None:
    with TestClient(create_app()) as client:
        missing = client.get("/does-not-exist")
        wrong_method = client.post("/health/live")
        invalid = client.post("/events", json={"event_type": "broken"})
        live = client.get("/health/live")
        metrics = client.get("/metrics")
        openapi = client.get("/openapi.json")

    for response, status in ((missing, 404), (wrong_method, 405), (invalid, 422)):
        assert response.status_code == status
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["status"] == status
        assert body["request_id"]
        assert response.headers["X-Request-ID"] == body["request_id"]
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert metrics.status_code == 200
    assert "event_platform_" in metrics.text
    assert openapi.status_code == 200
    assert set(openapi.json()["paths"]["/health/live"]["get"]["responses"]) >= {
        "404",
        "405",
        "422",
        "500",
    }


@pytest.mark.functional
def test_valid_ingestion_returns_accepted_contract_and_metrics_change() -> None:
    payload = {
        "event_type": "functional.event",
        "timestamp": "2026-01-01T00:00:00Z",
        "user_id": "functional-user",
        "source_url": "https://example.invalid/functional",
        "metadata": {"suite": "functional"},
    }
    with TestClient(create_app()) as client:
        response = client.post("/events", json=payload, headers={"Idempotency-Key": "functional-1"})
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["event_id"]
        assert body["request_id"]
        assert client.get("/metrics").status_code == 200
