"""Versioned Mongo storage bootstrap and verification semantics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import IndexModel

from event_platform.storage.bootstrap import (
    SCHEMA_DOCUMENT_ID,
    SCHEMA_VERSION,
    StorageCollections,
    StorageSchemaError,
    bootstrap_storage,
    storage_manifest,
    verify_storage,
)

pytestmark = pytest.mark.unit


class FakeIndexCursor:
    def __init__(self, indexes: list[Mapping[str, object]]) -> None:
        self._indexes = indexes

    async def to_list(self, length: int | None = None) -> list[Mapping[str, object]]:
        del length
        return list(self._indexes)


class FakeUpdateResult:
    matched_count = 1
    modified_count = 0


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {}
        self.indexes: dict[str, dict[str, object]] = {"_id_": {"name": "_id_", "key": {"_id": 1}}}
        self.error: Exception | None = None
        self.write_count = 0

    async def create_indexes(self, models: list[IndexModel]) -> list[str]:
        if self.error:
            raise self.error
        names: list[str] = []
        for model in models:
            document = dict(model.document)
            name = str(document["name"])
            key = document["key"]
            document["key"] = dict(key.items()) if hasattr(key, "items") else dict(key)
            existing = self.indexes.get(name)
            if existing is not None and existing != document:
                raise PyMongoError("SENTINEL_RAW_INDEX_CONFLICT")
            self.indexes[name] = document
            names.append(name)
        self.write_count += 1
        return names

    async def list_indexes(self) -> FakeIndexCursor:
        if self.error:
            raise self.error
        return FakeIndexCursor(list(self.indexes.values()))

    async def find_one(self, query: Mapping[str, object]) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        return self.documents.get(str(query.get("_id")))

    async def update_one(
        self,
        query: Mapping[str, object],
        update: Mapping[str, Mapping[str, object]],
        *,
        upsert: bool,
    ) -> FakeUpdateResult:
        if self.error:
            raise self.error
        assert upsert is True
        identifier = str(query["_id"])
        if identifier not in self.documents:
            self.documents[identifier] = {
                "_id": identifier,
                **dict(update["$setOnInsert"]),
            }
            self.write_count += 1
        return FakeUpdateResult()


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    async def list_collection_names(self) -> list[str]:
        return list(self.collections)

    async def create_collection(self, name: str) -> FakeCollection:
        return self[name]


def test_manifest_is_stable_and_covers_only_observed_access_paths() -> None:
    collections = StorageCollections(events="tenant_events")
    first = storage_manifest(collections)
    second = storage_manifest(collections)

    assert first.schema_version == SCHEMA_VERSION == 1
    assert first.fingerprint == second.fingerprint
    assert set(first.indexes) == {
        "tenant_events",
        "search_projection_checkpoints",
        "search_rebuilds",
        "search_rebuild_leases",
        "event_idempotency",
        "search_projection_leases",
        "storage_schema",
    }
    assert first.indexes["tenant_events"][0].name == "uq_events_event_id"
    assert [index.name for index in first.indexes["search_projection_checkpoints"]] == [
        "uq_search_projection_checkpoints_projector"
    ]
    assert [index.name for index in first.indexes["search_rebuilds"]] == [
        "uq_search_rebuilds_rebuild_id",
        "ix_search_rebuilds_started_at",
    ]
    assert all(
        "metadata" not in str(index) for indexes in first.indexes.values() for index in indexes
    )


@pytest.mark.asyncio
async def test_empty_storage_bootstrap_is_idempotent_and_verifiable() -> None:
    database = FakeDatabase()

    def clock() -> datetime:
        return datetime(2026, 9, 19, 18, 0, tzinfo=UTC)

    first = await bootstrap_storage(database, clock=clock)  # type: ignore[arg-type]
    state_writes = database["storage_schema"].write_count
    second = await bootstrap_storage(database, clock=clock)  # type: ignore[arg-type]
    verified = await verify_storage(database)  # type: ignore[arg-type]

    assert first == second == verified
    assert verified.schema_version == 1
    assert verified.verified_indexes == 13
    assert database["storage_schema"].write_count == state_writes
    assert database["storage_schema"].documents[SCHEMA_DOCUMENT_ID]["applied_at"] == clock()


@pytest.mark.asyncio
async def test_verification_rejects_missing_state_and_index_drift_safely() -> None:
    database = FakeDatabase()

    with pytest.raises(StorageSchemaError) as missing:
        await verify_storage(database)  # type: ignore[arg-type]
    assert missing.value.classification == "schema_state_missing"

    await bootstrap_storage(database)  # type: ignore[arg-type]
    database["events"].indexes["uq_events_event_id"]["unique"] = False
    with pytest.raises(StorageSchemaError) as mismatch:
        await verify_storage(database)  # type: ignore[arg-type]
    assert mismatch.value.classification == "index_definition_mismatch"
    assert mismatch.value.collection == "events"
    assert mismatch.value.index == "uq_events_event_id"
    assert "event_id" not in str(mismatch.value)


@pytest.mark.asyncio
async def test_verification_rejects_incompatible_version_and_manifest() -> None:
    database = FakeDatabase()
    await bootstrap_storage(database)  # type: ignore[arg-type]
    state = database["storage_schema"].documents[SCHEMA_DOCUMENT_ID]

    state["schema_version"] = 2
    with pytest.raises(StorageSchemaError) as version:
        await verify_storage(database)  # type: ignore[arg-type]
    assert version.value.classification == "schema_version_incompatible"

    state["schema_version"] = 1
    state["manifest_fingerprint"] = "0" * 64
    with pytest.raises(StorageSchemaError) as fingerprint:
        await verify_storage(database)  # type: ignore[arg-type]
    assert fingerprint.value.classification == "schema_manifest_mismatch"


@pytest.mark.asyncio
async def test_driver_failures_are_classified_without_raw_details() -> None:
    database = FakeDatabase()
    database["storage_schema"].error = PyMongoError("SENTINEL_RAW_CREDENTIAL")

    with pytest.raises(StorageSchemaError) as error:
        await verify_storage(database)  # type: ignore[arg-type]
    assert error.value.classification == "storage_dependency_unavailable"
    assert "SENTINEL" not in str(error.value)
    assert error.value.__cause__ is None

    conflict = FakeDatabase()
    conflict["events"].error = OperationFailure("SENTINEL_RAW_INDEX_CONFLICT")
    with pytest.raises(StorageSchemaError) as bootstrap_error:
        await bootstrap_storage(conflict)  # type: ignore[arg-type]
    assert bootstrap_error.value.classification == "storage_bootstrap_conflict"
    assert "SENTINEL" not in str(bootstrap_error.value)
