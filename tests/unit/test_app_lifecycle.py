"""Base application startup, liveness, and shutdown behavior."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from event_platform.core.logging import JsonLogFormatter
from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.search.search import ElasticsearchSearchService
from event_platform.storage.bootstrap import StorageSchemaError, StorageVerification


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
def test_swagger_ui_uses_only_local_assets() -> None:
    with TestClient(create_app()) as client:
        docs = client.get("/docs")
        redirect = client.get("/docs/oauth2-redirect")
        assets = {
            path: client.get(path)
            for path in (
                "/docs-assets/swagger-ui.css",
                "/docs-assets/swagger-ui-bundle.js",
                "/docs-assets/swagger-ui-standalone-preset.js",
                "/docs-assets/swagger-initializer.js",
                "/docs-assets/oauth2-redirect.js",
                "/docs-assets/favicon.svg",
            )
        }

    assert docs.status_code == 200
    assert "cdn.jsdelivr.net" not in docs.text
    assert "https://" not in docs.text
    assert "/docs-assets/swagger-ui.css" in docs.text
    assert "/docs-assets/swagger-ui-bundle.js" in docs.text
    assert "/docs-assets/swagger-ui-standalone-preset.js" in docs.text
    assert "/docs-assets/swagger-initializer.js" in docs.text
    assert redirect.status_code == 200
    assert "cdn.jsdelivr.net" not in redirect.text
    assert "/docs-assets/oauth2-redirect.js" in redirect.text
    assert all(response.status_code == 200 for response in assets.values())
    assert "https://" not in assets["/docs-assets/swagger-initializer.js"].text
    assert "validatorUrl: null" in assets["/docs-assets/swagger-initializer.js"].text
    assert assets["/docs-assets/swagger-ui.css"].headers["content-type"].startswith("text/css")
    assert (
        assets["/docs-assets/swagger-ui-bundle.js"]
        .headers["content-type"]
        .startswith("text/javascript")
    )


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


class _FakeMongoDatabase:
    def __getitem__(self, name: str) -> object:
        del name
        return object()


class _FakeMongoClient:
    def __init__(self) -> None:
        self.database = _FakeMongoDatabase()
        self.closed = False

    def __getitem__(self, name: str) -> _FakeMongoDatabase:
        del name
        return self.database

    async def close(self) -> None:
        self.closed = True


@pytest.mark.unit
def test_configured_mongo_is_verified_before_runtime_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from event_platform.core.settings import ServiceSettings

    mongo = _FakeMongoClient()
    calls: list[str] = []

    async def verify(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        calls.append("verify")
        return StorageVerification(1, "a" * 64, 10)

    monkeypatch.setattr("event_platform.main.AsyncMongoClient", lambda *args, **kwargs: mongo)
    monkeypatch.setattr("event_platform.main.verify_storage", verify)
    app = create_app(ServiceSettings(env="test", mongo_url="mongodb://mongo.test:27017"))

    with TestClient(app):
        assert calls == ["verify"]
        assert app.state.persistence_worker_ready is True

    assert mongo.closed is True


@pytest.mark.unit
def test_storage_verification_failure_aborts_startup_and_closes_mongo(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from event_platform.core.settings import ServiceSettings, SettingsStartupError

    mongo = _FakeMongoClient()

    async def fail(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        raise StorageSchemaError("index_missing", collection="events", index="uq_events_event_id")

    monkeypatch.setattr("event_platform.main.AsyncMongoClient", lambda *args, **kwargs: mongo)
    monkeypatch.setattr("event_platform.main.verify_storage", fail)

    with pytest.raises(SettingsStartupError):
        with TestClient(
            create_app(ServiceSettings(env="test", mongo_url="mongodb://mongo.test:27017"))
        ):
            pass

    assert mongo.closed is True
    failures = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "storage.verification_failed"
    ]
    assert failures[-1].classification == "index_missing"
    assert "mongodb://" not in failures[-1].getMessage()
