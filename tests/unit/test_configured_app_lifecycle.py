"""Exercise the configured application dependency graph without external services."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from event_platform.core.settings import ServiceSettings
from event_platform.main import create_app
from event_platform.storage.bootstrap import StorageVerification

pytestmark = pytest.mark.unit


class _Database:
    def __getitem__(self, _name: str) -> object:
        return object()


class _Mongo:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.admin = SimpleNamespace(command=self._command)
        self.closed = False
        self.database = _Database()

    async def _command(self, _name: str) -> dict[str, int]:
        return {"ok": 1}

    def __getitem__(self, _name: str) -> _Database:
        return self.database

    async def close(self) -> None:
        self.closed = True


class _Redis:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


class _Elasticsearch:
    def __init__(self) -> None:
        self.closed = False

    async def info(self) -> dict[str, str]:
        return {"status": "ok"}

    async def close(self) -> None:
        self.closed = True


class _Projector:
    def __init__(self, **_kwargs: object) -> None:
        self.stopped = False

    def set_ownership(self, **_kwargs: object) -> None:
        return None

    def set_target_index(self, _target: str | None) -> None:
        return None

    def change_stream_position(self) -> str:
        return "1:1"

    async def run_source(self, _source: object) -> None:
        await asyncio.Event().wait()

    def stop(self) -> None:
        self.stopped = True


class _LeaseStore:
    def __init__(self, *_args: object) -> None:
        self.released = False

    async def acquire(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(owner="owner", generation=1)

    async def renew(self, lease: object) -> object:
        return lease

    async def release(self, _lease: object) -> None:
        self.released = True


class _Source:
    def __init__(self, _collection: object, *, ready: asyncio.Event | None = None) -> None:
        if ready is not None:
            ready.set()

    async def begin_fence(self) -> object:
        return SimpleNamespace(latest_position=lambda: None)


class _RebuildSource:
    def __init__(self, *_args: object) -> None:
        pass

    async def capture_backfill_upper_bound(self) -> str | None:
        return None


class _Worker:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    async def run(self, stop_event: asyncio.Event) -> None:
        await stop_event.wait()


class _Rebuilder:
    def __init__(self, **_kwargs: object) -> None:
        pass


@pytest.mark.parametrize("dependency_timeout", [0.1])
def test_configured_lifespan_wires_mongo_redis_elasticsearch_projector_and_worker(
    monkeypatch: pytest.MonkeyPatch, dependency_timeout: float
) -> None:
    mongo = _Mongo()
    redis = _Redis()
    elasticsearch = _Elasticsearch()

    class RedisFactory:
        @staticmethod
        def from_url(*_args: object, **_kwargs: object) -> _Redis:
            return redis

    async def verify(*_args: object, **_kwargs: object) -> StorageVerification:
        return StorageVerification(1, "a" * 64, 10)

    monkeypatch.setattr("event_platform.main.AsyncMongoClient", lambda *_a, **_k: mongo)
    monkeypatch.setattr("event_platform.main.Redis", RedisFactory)
    monkeypatch.setattr(
        "event_platform.main.create_elasticsearch_client", lambda *_a, **_k: elasticsearch
    )
    monkeypatch.setattr("event_platform.main.verify_storage", verify)
    monkeypatch.setattr("event_platform.main.ensure_search_alias", lambda *_a, **_k: _done())
    monkeypatch.setattr("event_platform.main.MongoProjectionCheckpointStore", lambda *_a: object())
    monkeypatch.setattr("event_platform.main.MongoProjectionLeaseStore", _LeaseStore)
    monkeypatch.setattr("event_platform.main.MongoChangeStreamSource", _Source)
    monkeypatch.setattr("event_platform.main.MongoRebuildSource", _RebuildSource)
    monkeypatch.setattr(
        "event_platform.main.ElasticsearchProjectionWriter", lambda *_a, **_k: object()
    )
    monkeypatch.setattr("event_platform.main.ElasticsearchRebuildAdapter", lambda *_a: object())
    monkeypatch.setattr("event_platform.main.SearchProjector", _Projector)
    monkeypatch.setattr("event_platform.main.SearchRebuilder", _Rebuilder)
    monkeypatch.setattr("event_platform.main.PersistenceWorker", _Worker)

    settings = ServiceSettings(
        env="test",
        mongo_url="mongodb://mongo.test:27017",
        redis_url="redis://redis.test:6379/0",
        elasticsearch_url="http://es.test:9200",
        dependency_timeout_seconds=dependency_timeout,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/components").status_code == 200
        assert client.get("/metrics").status_code == 200

    assert mongo.closed
    assert redis.closed
    assert elasticsearch.closed


async def _done() -> None:
    return None
