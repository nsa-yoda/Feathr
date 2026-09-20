"""Feature 015 health and low-cardinality metrics coverage."""

import pytest
from fastapi.testclient import TestClient

from event_platform.main import create_app
from event_platform.observability.health import HealthRegistry
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
    assert "event_platform_request_latency_seconds" in metrics.text
    assert "event_platform_queue_depth" in metrics.text
    assert "event_platform_projection_lag_seconds" in metrics.text


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


def test_metrics_registry_histograms_and_gauges_are_bounded_and_current() -> None:
    registry = MetricsRegistry()
    registry.observe_http(method="GET", path="/events/search", status=200, duration_seconds=0.02)
    registry.observe_histogram("event_platform_request_latency_seconds", 2.0, {"route": "search"})
    registry.set_gauge("event_platform_queue_depth", 7)
    registry.set_gauge("event_platform_queue_depth", 2)

    rendered = registry.render()
    assert 'event_platform_request_latency_seconds_count{route="search"} 2' in rendered
    assert 'event_platform_request_latency_seconds_bucket{le="0.025",route="search"} 1' in rendered
    assert 'event_platform_request_latency_seconds_bucket{le="+Inf",route="search"} 2' in rendered
    assert 'event_platform_request_latency_seconds_max{route="search"} 2' in rendered
    assert "event_platform_queue_depth 2" in rendered
    assert "event_platform_queue_depth 7" not in rendered

    with pytest.raises(ValueError):
        registry.observe_histogram(
            "event_platform_request_latency_seconds", 0.1, {"route": "unbounded"}
        )
    with pytest.raises(ValueError):
        registry.set_gauge("event_platform_queue_depth", -1)


@pytest.mark.asyncio
async def test_health_probes_run_concurrently_and_obey_deadline() -> None:
    import asyncio

    registry = HealthRegistry(probe_timeout=0.01, overall_timeout=0.03)
    started = 0

    async def slow() -> bool:
        nonlocal started
        started += 1
        await asyncio.sleep(0.05)
        return True

    registry.set_probe("mongo", slow)
    registry.set_probe("redis", slow)
    snapshot = await registry.snapshot()
    assert started == 2
    assert snapshot.components.mongo.detail == "probe_failed"
    assert snapshot.components.redis.detail == "probe_failed"
