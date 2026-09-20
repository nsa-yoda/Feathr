"""Real MongoDB lifecycle coverage for versioned storage bootstrap."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pymongo import AsyncMongoClient

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.storage.bootstrap import (
    SCHEMA_DOCUMENT_ID,
    StorageCollections,
    StorageSchemaError,
    bootstrap_storage,
    verify_storage,
)
from event_platform.storage.mongo import EventAlreadyExists, MongoEventStore
from tests.integration.support import new_namespace, require_mongo

pytestmark = pytest.mark.integration


def _event() -> CanonicalEvent:
    value = EventInput.model_validate(
        {
            "event_type": "bootstrap.proof",
            "timestamp": "2026-09-19T18:00:00Z",
            "user_id": "bootstrap-user",
            "source_url": "https://example.test/bootstrap",
            "metadata": {"proof": True},
        }
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID("00000000-0000-0000-0000-000000000026"),
        ingested_at=datetime(2026, 9, 19, 18, 0, tzinfo=UTC),
    )


def _index_names(plan: object) -> set[str]:
    names: set[str] = set()
    if isinstance(plan, dict):
        if isinstance(plan.get("indexName"), str):
            names.add(plan["indexName"])
        for value in plan.values():
            names.update(_index_names(value))
    elif isinstance(plan, list):
        for value in plan:
            names.update(_index_names(value))
    return names


@pytest.mark.asyncio
async def test_real_mongo_bootstrap_verification_uniqueness_and_query_plan() -> None:
    uri = os.getenv("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI is not configured")
    await require_mongo(uri)

    client = AsyncMongoClient(uri)
    namespace = new_namespace()
    database = client[namespace.database]
    collections = StorageCollections(events=namespace.collection)
    try:
        with pytest.raises(StorageSchemaError) as absent:
            await verify_storage(database, collections=collections)  # type: ignore[arg-type]
        assert absent.value.classification == "schema_state_missing"

        results = await asyncio.gather(
            *(bootstrap_storage(database, collections=collections) for _ in range(4))  # type: ignore[arg-type]
        )
        assert len({result.manifest_fingerprint for result in results}) == 1
        assert all(result.verified_indexes == 10 for result in results)
        assert await bootstrap_storage(database, collections=collections) == results[0]  # type: ignore[arg-type]

        store = MongoEventStore(database[collections.events])
        event = _event()
        await store.insert(event)
        with pytest.raises(EventAlreadyExists):
            await store.insert(event)

        index_documents = await (await database[collections.events].list_indexes()).to_list(
            length=None
        )
        assert {item["name"] for item in index_documents} >= {
            "uq_events_event_id",
            "ix_events_timestamp_event_id",
            "ix_events_event_type_timestamp_event_id",
            "ix_events_user_id_timestamp_event_id",
            "ix_events_source_url_timestamp_event_id",
        }
        checkpoint_indexes = await (await database[collections.checkpoints].list_indexes()).to_list(
            length=None
        )
        assert {item["name"] for item in checkpoint_indexes} >= {
            "uq_search_projection_checkpoints_projector"
        }
        rebuild_indexes = await (await database[collections.rebuilds].list_indexes()).to_list(
            length=None
        )
        assert {item["name"] for item in rebuild_indexes} >= {
            "uq_search_rebuilds_rebuild_id",
            "ix_search_rebuilds_started_at",
        }

        explanation = await database.command(
            {
                "explain": {
                    "find": collections.events,
                    "filter": {"event_type": "bootstrap.proof"},
                    "sort": {"timestamp": -1, "event_id": -1},
                },
                "verbosity": "queryPlanner",
            }
        )
        assert "ix_events_event_type_timestamp_event_id" in _index_names(explanation)

        before_state = await database[collections.schema].find_one({"_id": SCHEMA_DOCUMENT_ID})
        before_indexes = {
            name: await (await database[name].list_indexes()).to_list(length=None)
            for name in (
                collections.events,
                collections.checkpoints,
                collections.rebuilds,
                collections.rebuild_leases,
                collections.schema,
            )
        }
        verified = await verify_storage(database, collections=collections)  # type: ignore[arg-type]
        assert verified == results[0]
        assert (
            await database[collections.schema].find_one({"_id": SCHEMA_DOCUMENT_ID}) == before_state
        )
        assert {
            name: await (await database[name].list_indexes()).to_list(length=None)
            for name in before_indexes
        } == before_indexes

        await database[collections.schema].update_one(
            {"_id": SCHEMA_DOCUMENT_ID}, {"$set": {"schema_version": 2}}
        )
        with pytest.raises(StorageSchemaError) as incompatible:
            await verify_storage(database, collections=collections)  # type: ignore[arg-type]
        assert incompatible.value.classification == "schema_version_incompatible"
    finally:
        try:
            await database.drop()
        finally:
            await client.close()
