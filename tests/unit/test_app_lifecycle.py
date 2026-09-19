"""Base application startup, liveness, and shutdown behavior."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from event_platform.core.logging import JsonLogFormatter
from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.search.search import ElasticsearchSearchService


@pytest.mark.unit
def test_base_app_serves_liveness_and_api_description() -> None:
    app = create_app()

    with TestClient(app) as client:
        liveness = client.get("/health/live")
        assert liveness.status_code == 200
        assert liveness.json() == {"status": "alive"}

        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert "/health/live" in openapi.json()["paths"]

        docs = client.get("/docs")
        assert docs.status_code == 200


@pytest.mark.unit
def test_base_app_lifespan_exits_cleanly() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
    assert not hasattr(app.state, "settings")


def test_lifespan_emits_structured_state_events(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="event_platform.lifecycle"):
        with TestClient(create_app(ServiceSettings(env="test", log_level="INFO"))):
            pass

    lifecycle_records = [
        record for record in caplog.records if record.name == "event_platform.lifecycle"
    ]
    events = {record.event for record in lifecycle_records}
    assert events == {
        "service.startup",
        "service.shutdown",
        "lifecycle.running",
        "lifecycle.draining",
        "lifecycle.queue_depth",
    }
    for record in lifecycle_records:
        structured = json.loads(JsonLogFormatter().format(record))
        assert structured["event"] in events
        assert structured["service"] == "event_platform"
        assert structured["logger"] == "event_platform.lifecycle"


def test_configured_elasticsearch_search_service_is_owned_by_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeElasticsearch:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[dict[str, object]] = []

        async def info(self) -> dict[str, str]:
            return {"status": "ok"}

        async def close(self) -> None:
            self.closed = True

        async def search(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(kwargs)
            return {"hits": {"hits": []}}

    client = FakeElasticsearch()
    monkeypatch.setattr(
        "event_platform.main.create_elasticsearch_client", lambda *args, **kwargs: client
    )
    app = create_app(
        ServiceSettings(
            env="test", elasticsearch_url="http://es.test", elasticsearch_alias="events-feature019"
        )
    )

    with TestClient(app) as test_client:
        assert isinstance(app.state.search_service, ElasticsearchSearchService)
        response = test_client.get("/events/search?q=term")
        assert response.status_code == 200

    assert not hasattr(app.state, "search_service")
    assert client.closed is True
    assert client.calls[0]["index"] == "events-feature019"
