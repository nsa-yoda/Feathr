"""Unit coverage for the typed Mongo storage boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.operations import IndexModel

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.storage.mongo import (
    REQUIRED_INDEXES,
    EventAlreadyExists,
    EventQuery,
    InvalidAggregation,
    MongoDependencyError,
    MongoEventStore,
    _query_filter,
    _validated_pipeline,
    event_from_document,
    event_to_document,
    index_models,
)

pytestmark = pytest.mark.unit


def make_event(*, idempotency_key: str | None = None) -> CanonicalEvent:
    input_event = EventInput.model_validate(
        {
            "event_type": "pageview",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "user-1",
            "source_url": "https://example.test/page",
            "metadata": {"nested": {"ok": True}},
        }
    )
    return CanonicalEvent.from_input(
        input_event,
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        idempotency_key=idempotency_key,
    )


class FakeCursor:
    def __init__(self, documents: list[Mapping[str, object]]) -> None:
        self.documents = documents
        self.sort_spec: object = None
        self.limit_value: int | None = None

    def sort(self, spec: object) -> FakeCursor:
        self.sort_spec = spec
        return self

    def limit(self, value: int) -> FakeCursor:
        self.limit_value = value
        return self

    def __aiter__(self) -> FakeCursor:
        return self

    async def __anext__(self) -> Mapping[str, object]:
        if not self.documents:
            raise StopAsyncIteration
        return self.documents.pop(0)

    async def to_list(self, length: int | None = None) -> list[Mapping[str, object]]:
        del length
        return self.documents


class FakeCollection:
    def __init__(self, documents: list[Mapping[str, object]] | None = None) -> None:
        self.documents = documents or []
        self.last_filter: Mapping[str, object] | None = None
        self.last_cursor: FakeCursor | None = None
        self.index_models: tuple[IndexModel, ...] = ()
        self.error: Exception | None = None

    async def insert_one(self, document: Mapping[str, object]) -> None:
        if self.error:
            raise self.error
        self.documents.append(document)

    async def find_one(self, query: Mapping[str, object]) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        self.last_filter = query
        return self.documents[0] if self.documents else None

    def find(self, query: Mapping[str, object]) -> FakeCursor:
        if self.error:
            raise self.error
        self.last_filter = query
        self.last_cursor = FakeCursor(list(self.documents))
        return self.last_cursor

    async def aggregate(self, stages: list[Mapping[str, object]], **options: object) -> FakeCursor:
        if self.error:
            raise self.error
        self.last_filter = {"pipeline": stages, **options}
        return FakeCursor(list(self.documents))

    async def create_indexes(self, models: list[IndexModel]) -> list[str]:
        if self.error:
            raise self.error
        self.index_models = models
        return [model.document["name"] for model in models]


def test_query_validation_and_predicate_are_typed_and_exclusive() -> None:
    now = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    query = EventQuery(
        event_type="pageview",
        timestamp_from=now,
        timestamp_to=now,
        after_timestamp=now,
        after_event_id=UUID("00000000-0000-0000-0000-000000000001"),
        limit=25,
    )
    predicate = _query_filter(query)

    assert predicate["$and"]  # type: ignore[index]
    assert any("$or" in item for item in predicate["$and"])  # type: ignore[operator]
    with pytest.raises(ValidationError):
        EventQuery(after_event_id=uuid4())
    with pytest.raises(ValidationError):
        EventQuery(limit=0)
    with pytest.raises(ValidationError):
        EventQuery(limit=1_001)
    with pytest.raises(ValidationError):
        EventQuery(timestamp_from=now + timedelta(days=1), timestamp_to=now)
    with pytest.raises(ValidationError):
        EventQuery(timestamp_from=now.replace(tzinfo=None))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_type", "signup"),
        ("user_id", "user-2"),
        ("source_url", "https://example.test/other"),
    ],
)
def test_each_supported_filter_is_preserved(field: str, value: str) -> None:
    assert _query_filter(EventQuery(**{field: value})) == {field: value}


def test_query_validation_errors_do_not_echo_filter_values() -> None:
    sentinel = "SENTINEL_QUERY_VALUE"
    with pytest.raises(ValidationError) as error:
        EventQuery(event_type=sentinel * 20)
    assert sentinel not in str(error.value)

    with pytest.raises(ValidationError) as error:
        EventQuery.model_validate({"unexpected": sentinel})
    assert sentinel not in str(error.value)


def test_event_bson_mapping_round_trips_without_mongo_id() -> None:
    event = make_event(idempotency_key="secret-key")
    document = event_to_document(event)
    restored = event_from_document({**document, "_id": object()})

    assert document == {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "user_id": event.user_id,
        "source_url": str(event.source_url),
        "metadata": {"nested": {"ok": True}},
        "ingested_at": event.ingested_at,
        "schema_version": 1,
        "payload_hash": event.payload_hash,
        "idempotency_key_hash": event.idempotency_key_hash,
    }
    assert restored == event
    invalid = dict(document)
    invalid["event_id"] = "not-a-uuid"
    with pytest.raises(MongoDependencyError):
        event_from_document(invalid)

    normalized = _query_filter(EventQuery(source_url="https://example.test"))
    assert normalized == {"source_url": "https://example.test/"}


@pytest.mark.asyncio
async def test_store_insert_fetch_query_aggregate_and_indexes() -> None:
    collection = FakeCollection([event_to_document(make_event())])
    store = MongoEventStore(collection)  # type: ignore[arg-type]

    await store.insert(make_event())
    fetched = await store.get_by_id(make_event().event_id)
    assert fetched is not None
    assert await MongoEventStore(FakeCollection()).get_by_id(uuid4()) is None  # type: ignore[arg-type]

    results = [item async for item in store.query(EventQuery(limit=7))]
    assert results
    assert collection.last_cursor is not None
    assert collection.last_cursor.limit_value == 7
    assert collection.last_cursor.sort_spec == [("timestamp", -1), ("event_id", -1)]
    assert await store.aggregate([])
    assert await store.aggregate([{"$match": {"event_type": "pageview"}}], max_time_ms=5_000)
    assert collection.last_filter is not None
    assert collection.last_filter["maxTimeMS"] == 5_000

    names = await store.ensure_indexes()
    assert names == tuple(index.name for index in REQUIRED_INDEXES)
    assert len(collection.index_models) == 5
    assert await store.ensure_indexes() == names


@pytest.mark.asyncio
async def test_store_translates_driver_errors_and_rejects_bad_pipelines() -> None:
    duplicate = FakeCollection()
    duplicate.error = DuplicateKeyError("raw duplicate secret")
    with pytest.raises(EventAlreadyExists) as duplicate_error:
        await MongoEventStore(duplicate).insert(make_event())  # type: ignore[arg-type]
    assert "raw duplicate" not in str(duplicate_error.value)
    assert duplicate_error.value.__cause__ is None

    dependency = FakeCollection()
    dependency.error = PyMongoError("raw connection secret")
    with pytest.raises(MongoDependencyError) as dependency_error:
        await MongoEventStore(dependency).get_by_id(uuid4())  # type: ignore[arg-type]
    assert "raw connection" not in str(dependency_error.value)
    assert dependency_error.value.__cause__ is None

    for operation in ("query", "aggregate", "ensure_indexes"):
        failed = FakeCollection()
        failed.error = PyMongoError("raw operation secret")
        store = MongoEventStore(failed)  # type: ignore[arg-type]
        with pytest.raises(MongoDependencyError) as operation_error:
            if operation == "query":
                [item async for item in store.query(EventQuery())]
            elif operation == "aggregate":
                await store.aggregate([])
            else:
                await store.ensure_indexes()
        assert "raw operation" not in str(operation_error.value)

    with pytest.raises(InvalidAggregation):
        await MongoEventStore(FakeCollection()).aggregate([{}])  # type: ignore[arg-type]
    with pytest.raises(InvalidAggregation):
        await MongoEventStore(FakeCollection()).aggregate("bad")  # type: ignore[arg-type]
    with pytest.raises(InvalidAggregation):
        await MongoEventStore(FakeCollection()).aggregate([1])  # type: ignore[arg-type]
    with pytest.raises(InvalidAggregation):
        await MongoEventStore(FakeCollection()).aggregate(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidAggregation):
        await MongoEventStore(FakeCollection()).aggregate([], max_time_ms=0)
    assert _validated_pipeline([]) == []


def test_index_models_are_exact_and_do_not_include_metadata_or_wildcards() -> None:
    models = index_models()
    expected = {
        "uq_events_event_id": {"key": {"event_id": 1}, "unique": True},
        "ix_events_timestamp_event_id": {"key": {"timestamp": -1, "event_id": -1}},
        "ix_events_event_type_timestamp_event_id": {
            "key": {"event_type": 1, "timestamp": -1, "event_id": -1}
        },
        "ix_events_user_id_timestamp_event_id": {
            "key": {"user_id": 1, "timestamp": -1, "event_id": -1}
        },
        "ix_events_source_url_timestamp_event_id": {
            "key": {"source_url": 1, "timestamp": -1, "event_id": -1}
        },
    }
    assert {model.document["name"] for model in models} == set(expected)
    for model in models:
        definition = expected[model.document["name"]]
        assert model.document["key"] == definition["key"]
        assert model.document.get("unique", False) == definition.get("unique", False)
    assert all("metadata" not in str(model.document) for model in models)
    assert all("$**" not in str(model.document) for model in models)
