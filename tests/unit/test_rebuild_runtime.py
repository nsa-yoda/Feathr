"""Executable dependency-graph coverage for the rebuild command runtime."""

import asyncio
from types import SimpleNamespace

import pytest

from event_platform.core.settings import ServiceSettings
from event_platform.search.rebuild import RebuildError
from event_platform.search.rebuild_runtime import configured_rebuild_runtime


class _Collection:
    def __init__(self, name: str) -> None:
        self.name = name


class _Database:
    def __getitem__(self, name: str) -> _Collection:
        return _Collection(name)


class _Mongo:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.closed = False

    def __getitem__(self, _name: str) -> _Database:
        return _Database()

    async def close(self) -> None:
        self.closed = True


class _Elasticsearch:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _LeaseStore:
    released = False

    def __init__(self, _collection: object) -> None:
        pass

    async def acquire(self, *, projector: str, owner: str) -> object:
        return SimpleNamespace(projector=projector, owner=owner, generation=1)

    async def release(self, _lease: object) -> None:
        self.released = True


class _Checkpoint:
    def __init__(self, _collection: object) -> None:
        pass


class _Source:
    def __init__(self, _collection: object) -> None:
        pass

    async def capture_backfill_upper_bound(self) -> str | None:
        return None


class _ChangeSource:
    def __init__(self, _collection: object) -> None:
        pass

    async def begin_fence(self) -> object:
        return SimpleNamespace(latest_position=lambda: None)


class _State:
    def __init__(self, *_args: object) -> None:
        pass


class _Projector:
    def __init__(self, **_kwargs: object) -> None:
        self.position = None
        self.stopped = False

    def set_ownership(self, **_kwargs: object) -> None:
        pass

    def set_target_index(self, _target: str | None) -> None:
        pass

    def change_stream_position(self) -> str | None:
        return self.position

    async def run_source(self, _source: object) -> None:
        await asyncio.Event().wait()

    def stop(self) -> None:
        self.stopped = True


@pytest.mark.unit
def test_rebuild_runtime_requires_canonical_and_projection_urls() -> None:
    settings = ServiceSettings(env="test")
    with pytest.raises(RebuildError, match="rebuild_unexpected_failure"):
        asyncio.run(_enter_runtime(settings))


async def _enter_runtime(settings: ServiceSettings) -> None:
    async with configured_rebuild_runtime(settings):
        pass


@pytest.mark.unit
def test_rebuild_runtime_constructs_and_closes_owned_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    mongo = _Mongo()
    elasticsearch = _Elasticsearch()
    lease_store = _LeaseStore(None)
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.AsyncMongoClient", lambda *_a, **_k: mongo
    )
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.create_client", lambda *_a, **_k: elasticsearch
    )
    monkeypatch.setattr("event_platform.search.rebuild_runtime.ensure_search_alias", _noop)
    monkeypatch.setattr("event_platform.search.rebuild_runtime.MongoRebuildSource", _Source)
    monkeypatch.setattr("event_platform.search.rebuild_runtime.MongoRebuildStore", _State)
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.MongoProjectionCheckpointStore", _Checkpoint
    )
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.MongoProjectionLeaseStore", lambda _c: lease_store
    )
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.MongoChangeStreamSource", _ChangeSource
    )
    monkeypatch.setattr("event_platform.search.rebuild_runtime.SearchProjector", _Projector)
    monkeypatch.setattr(
        "event_platform.search.rebuild_runtime.ElasticsearchProjectionWriter",
        lambda *_a, **_k: object(),
    )

    settings = ServiceSettings(
        env="test",
        mongo_url="mongodb://mongo.test",
        elasticsearch_url="http://es.test",
    )
    asyncio.run(_enter_runtime(settings))
    assert mongo.closed is True
    assert elasticsearch.closed is True
    assert lease_store.released is True


async def _noop(*_args: object, **_kwargs: object) -> None:
    return None
