"""Feature 015 health and low-cardinality metrics coverage."""

import pytest
from fastapi.testclient import TestClient

from event_platform.main import create_app
from event_platform.observability.metrics import MetricsRegistry

pytestmark = pytest.mark.unit


def test_liveness_is_cheap_and_metrics_are_prometheus_text() -> None:
    with TestClient(create_app()) as client:
        live = client.get("/health/live")
        client.get("/health/components")
        metrics = client.get("/metrics")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
    assert "event_platform_http_requests_total" in metrics.text
    assert "event_platform_lifecycle_events_total" in metrics.text
    assert "event_platform_mongo_operations_total" in metrics.text
    assert "event_platform_queue_operations_total" in metrics.text
    assert "event_platform_redis_operations_total" in metrics.text


def test_readiness_requires_mongo_but_components_expose_safe_degraded_states() -> None:
    with TestClient(create_app()) as client:
        ready = client.get("/health/ready")
        components = client.get("/health/components")

    assert ready.status_code == 503
    assert ready.json()["components"]["mongo"] == {
        "state": "unhealthy",
        "detail": "unavailable",
    }
    assert components.status_code == 200
    assert "exception" not in components.text.lower()


def test_readiness_accepts_es_and_redis_degradation_when_core_is_healthy() -> None:
    app = create_app()
    with TestClient(app) as client:
        for component in ("mongo", "queue", "persistence_worker"):
            app.state.health.set_probe(component, lambda: True)
        app.state.health.set_probe("elasticsearch", lambda: "degraded")
        app.state.health.set_probe("redis", lambda: "degraded")
        ready = client.get("/health/ready")
        components = client.get("/health/components")

    assert ready.status_code == 200
    assert ready.json()["status"] == "degraded"
    assert components.json()["components"]["elasticsearch"]["state"] == "degraded"


def test_metrics_never_use_raw_identifier_paths() -> None:
    with TestClient(create_app()) as client:
        client.get("/events/12345678-1234-4234-8234-123456789abc")
        metrics = client.get("/metrics")

    assert "12345678-1234-4234-8234-123456789abc" not in metrics.text
    assert 'route="events_detail"' in metrics.text


def test_metrics_registry_rejects_unknown_families_and_normalizes_methods() -> None:
    registry = MetricsRegistry()
    with pytest.raises(ValueError):
        registry.inc("custom_metric", {"outcome": "success"})  # type: ignore[arg-type]
    registry.observe_http(method="TRACE", path="/health/live", status=200)
    assert 'method="OTHER"' in registry.render()
