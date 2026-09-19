from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.projection import SearchProjector
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.mongo import event_to_document

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_mongo_change_stream_projector_and_elasticsearch_target() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")

    mongo = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    database = mongo.get_database("event_platform_test")
    events = database.get_collection("events")
    checkpoints = database.get_collection("projection_checkpoints")
    suffix = uuid4().hex
    alias = f"events-feature010-{suffix}"
    target = f"events-feature010-target-{suffix}"
    projector_name = f"events-search-{suffix}"
    event_input = EventInput.model_validate(
        {
            "event_type": "pageview",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "integration-user",
            "source_url": "https://example.test/integration",
            "metadata": {"source": "feature010"},
        }
    )
    event = CanonicalEvent.from_input(
        event_input,
        event_id=uuid4(),
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )
    run_task = None
    try:
        try:
            await mongo.admin.command("ping")
            await es.info()
        except (ConnectionError, OSError, RuntimeError, PyMongoError, TransportError) as error:
            await es.close()
            await mongo.close()
            pytest.skip(f"integration services unavailable: {type(error).__name__}")

        checkpoint = MongoProjectionCheckpointStore(checkpoints)
        projector = SearchProjector(
            projector=projector_name,
            checkpoint=checkpoint,
            writer=ElasticsearchProjectionWriter(es, alias=alias),
            target_index=target,
        )
        stream_ready = asyncio.Event()
        source = MongoChangeStreamSource(events, ready=stream_ready)
        run_task = asyncio.create_task(projector.run_source(source))
        await asyncio.wait_for(stream_ready.wait(), timeout=5)
        await events.insert_one(event_to_document(event))

        stored = None
        for _ in range(100):
            stored = await checkpoint.load(projector_name)
            if stored is not None:
                break
            await asyncio.sleep(0.05)
        assert stored is not None
        assert stored.projector == projector_name
        assert stored.state == "running"
        assert stored.last_projected_event_at == event.timestamp
        assert stored.resume_token
        assert projector.status().checkpoint_present is True
        assert (await es.get(index=alias, id=str(event.event_id)))["_source"]["event_id"] == str(
            event.event_id
        )
        assert (await es.get(index=target, id=str(event.event_id)))["_source"]["event_id"] == str(
            event.event_id
        )

        projector.stop()
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
    finally:
        if run_task is not None and not run_task.done():
            run_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run_task
        for index in (alias, target):
            try:
                await es.indices.delete(index=index, ignore_status=404)
            except (ConnectionError, OSError, TransportError):
                pass
        try:
            await events.delete_one({"event_id": str(event.event_id)})
            await checkpoints.delete_one({"projector": projector_name})
        except (ConnectionError, OSError, PyMongoError):
            pass
        await es.close()
        await mongo.close()
