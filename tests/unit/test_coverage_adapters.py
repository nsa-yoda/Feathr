"""Risk-focused coverage for service adapters and durable state boundaries."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest
from bson import ObjectId
from bson.timestamp import Timestamp
from elastic_transport import TransportError
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.projection import (
    InvalidResumeHistory,
    MalformedChange,
    ProjectionError,
)
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.projection_leases import MongoProjectionLeaseStore, ProjectionLeaseError
from event_platform.storage.rebuild_source import MongoRebuildSource

pytestmark = pytest.mark.unit


def _event_document() -> dict[str, object]:
    value = EventInput.model_validate(
        {
            "event_type": "view",
            "timestamp": "2026-01-01T00:00:00Z",
            "user_id": "user-1",
            "source_url": "https://example.test",
            "metadata": {"source": "coverage"},
        }
    )
    event = CanonicalEvent.from_input(
        value,
        event_id=UUID(int=1),
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    from event_platform.storage.mongo import event_to_document

    return event_to_document(event)


class _AsyncCursor:
    def __init__(self, documents: list[Mapping[str, object]]) -> None:
        self.documents = documents

    def sort(self, *_args: object, **_kwargs: object) -> _AsyncCursor:
        return self

    def __aiter__(self) -> AsyncIterator[Mapping[str, object]]:
        async def items() -> AsyncIterator[Mapping[str, object]]:
            for document in self.documents:
                yield document

        return items()


class _RebuildCollection:
    database: object | None = None

    def __init__(self, documents: list[Mapping[str, object]]) -> None:
        self.documents = documents
        self.queries: list[Mapping[str, object]] = []
        self.with_options_calls = 0

    def with_options(self, **_kwargs: object) -> _RebuildCollection:
        self.with_options_calls += 1
        return self

    async def find_one(self, *args: object, **kwargs: object) -> Mapping[str, object] | None:
        del args, kwargs
        if not self.documents:
            return None
        return {"_id": self.documents[-1]["_id"]}

    def find(self, query: Mapping[str, object]) -> _AsyncCursor:
        self.queries.append(query)
        return _AsyncCursor(self.documents)


@pytest.mark.asyncio
async def test_mongo_rebuild_source_uses_majority_bound_and_scans_identities() -> None:
    document = _event_document()
    document["_id"] = ObjectId("507f1f77bcf86cd799439011")
    collection = _RebuildCollection([document])
    source = MongoRebuildSource(collection)  # type: ignore[arg-type]

    bound = await source.capture_backfill_upper_bound()
    assert bound == "507f1f77bcf86cd799439011"
    scanned = [item async for item in source.scan(backfill_upper_bound=bound)]
    assert len(scanned) == 1
    assert collection.with_options_calls == 2
    assert collection.queries[-1]["_id"] == {"$lte": ObjectId(bound)}

    empty = MongoRebuildSource(_RebuildCollection([]))  # type: ignore[arg-type]
    assert await empty.capture_high_water() is None


@pytest.mark.asyncio
async def test_mongo_rebuild_source_rejects_non_objectid_canonical_ids() -> None:
    collection = _RebuildCollection([{"_id": "not-object-id"}])
    with pytest.raises(ValueError, match="ObjectId"):
        await MongoRebuildSource(collection).capture_backfill_upper_bound()  # type: ignore[arg-type]


class _Indices:
    def __init__(self) -> None:
        self.refresh_calls: list[str] = []
        self.error: Exception | None = None

    async def refresh(self, *, index: str) -> None:
        self.refresh_calls.append(index)
        if self.error:
            raise self.error


class _SearchClient:
    def __init__(self) -> None:
        self.indices = _Indices()
        self.responses: list[Mapping[str, object]] = []
        self.error: Exception | None = None
        self.closed = False

    async def search(self, **_kwargs: object) -> Mapping[str, object]:
        if self.error:
            raise self.error
        return self.responses.pop(0)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_elasticsearch_rebuild_adapter_reconciles_ids_and_paginates() -> None:
    client = _SearchClient()
    client.responses = [
        {
            "hits": {
                "hits": [
                    {"_id": "one", "sort": ["one"]},
                    {"_source": {"event_id": "two"}, "sort": ["two"]},
                ]
            }
        },
        {"hits": {"hits": []}},
    ]
    adapter = ElasticsearchRebuildAdapter(client)  # type: ignore[arg-type]
    assert [item async for item in adapter.iter_event_ids("candidate")] == ["one", "two"]
    assert client.indices.refresh_calls == ["candidate"]
    await adapter.close()
    assert client.closed


@pytest.mark.asyncio
async def test_elasticsearch_rebuild_adapter_rejects_malformed_id_pages_and_transport_errors() -> (
    None
):
    client = _SearchClient()
    adapter = ElasticsearchRebuildAdapter(client)  # type: ignore[arg-type]
    for response in (
        {"hits": []},
        {"hits": {"hits": [{}]}},
        {"hits": {"hits": [{"_id": "one"}]}},
    ):
        client.responses = [response]
        with pytest.raises(Exception, match="count_invalid"):
            _ = [item async for item in adapter.iter_event_ids("candidate")]

    client.indices.error = TransportError("down", ())
    with pytest.raises(Exception, match="elasticsearch_unavailable"):
        _ = [item async for item in adapter.iter_event_ids("candidate")]


class _Stream:
    def __init__(self, changes: list[Mapping[str, object]], error: Exception | None = None) -> None:
        self.changes = list(changes)
        self.error = error
        self.closed = False

    async def __aenter__(self) -> _Stream:
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[Mapping[str, object]]:
        async def items() -> AsyncIterator[Mapping[str, object]]:
            while self.changes:
                yield self.changes.pop(0)
            if self.error:
                raise self.error

        return items()

    async def try_next(self) -> Mapping[str, object] | None:
        if self.error:
            error, self.error = self.error, None
            raise error
        return self.changes.pop(0) if self.changes else None

    async def close(self) -> None:
        self.closed = True


class _ChangeCollection:
    def __init__(self, streams: list[_Stream]) -> None:
        self.streams = streams
        self.watch_calls: list[dict[str, object]] = []

    async def watch(self, pipeline: object, **kwargs: object) -> _Stream:
        self.watch_calls.append({"pipeline": pipeline, **kwargs})
        return self.streams.pop(0)


def _change() -> dict[str, object]:
    document = _event_document()
    document["_id"] = ObjectId("507f1f77bcf86cd799439011")
    return {
        "_id": {"_data": "token"},
        "operationType": "insert",
        "fullDocument": document,
        "clusterTime": Timestamp(100, 7),
    }


@pytest.mark.asyncio
async def test_change_stream_source_decodes_resume_latest_and_fence_positions() -> None:
    ready = __import__("asyncio").Event()
    collection = _ChangeCollection([_Stream([_change()]), _Stream([_change()]), _Stream([])])
    source = MongoChangeStreamSource(collection, ready=ready)  # type: ignore[arg-type]
    changes = [item async for item in source.stream(resume_after={"_data": "old"})]
    assert len(changes) == 1
    assert changes[0].change_stream_position == "100:7"
    assert ready.is_set()
    assert collection.watch_calls[0]["resume_after"] == {"_data": "old"}
    assert await source.latest_position(resume_after=None) == "100:7"
    fence = await source.begin_fence()
    assert await fence.latest_position() is None


@pytest.mark.asyncio
async def test_change_stream_source_classifies_invalid_resume_and_malformed_changes() -> None:
    invalid = _ChangeCollection([_Stream([], PyMongoError("resume history lost"))])
    with pytest.raises(InvalidResumeHistory):
        _ = [item async for item in MongoChangeStreamSource(invalid).stream()]

    malformed = _ChangeCollection([_Stream([{"operationType": "update"}])])
    with pytest.raises(MalformedChange):
        _ = [item async for item in MongoChangeStreamSource(malformed).stream()]

    dependency = _ChangeCollection([_Stream([], PyMongoError("network down"))])
    with pytest.raises(ProjectionError, match="dependency_unavailable"):
        _ = [item async for item in MongoChangeStreamSource(dependency).stream()]


class _LeaseResult:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count


class _LeaseCollection:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.document: dict[str, object] | None = None

    async def find_one(self, _query: Mapping[str, object]) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        return self.document

    async def find_one_and_update(self, *_args: object, **_kwargs: object) -> Mapping[str, object]:
        if self.error:
            raise self.error
        self.document = {"owner": "owner", "generation": 1}
        return self.document

    async def update_one(self, *_args: object, **_kwargs: object) -> _LeaseResult:
        if self.error:
            raise self.error
        return _LeaseResult()

    async def delete_one(self, *_args: object, **_kwargs: object) -> None:
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_projection_lease_store_validates_arguments_and_classifies_dependency_errors() -> (
    None
):
    collection = _LeaseCollection()
    store = MongoProjectionLeaseStore(collection)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await store.acquire(projector="", owner="owner")
    lease = await store.acquire(projector="events-search", owner="owner")
    assert lease is not None
    collection.error = PyMongoError("down")
    with pytest.raises(ProjectionLeaseError, match="renew_projection_lease"):
        await store.renew(lease)
    with pytest.raises(ProjectionLeaseError, match="release_projection_lease"):
        await store.release(lease)
