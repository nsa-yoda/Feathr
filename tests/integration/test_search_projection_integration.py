from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.projection import ProjectionStatus, SearchProjector
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.mongo import event_to_document
from tests.integration.support import (
    delete_es_index,
    drop_database,
    new_namespace,
    poll_until,
    require_elasticsearch,
    require_mongo,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_mongo_change_stream_projector_and_elasticsearch_target() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")
    await require_mongo(mongo_uri, require_replica_set=True)
    await require_elasticsearch(elasticsearch_url)

    mongo = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    namespace = new_namespace()
    database = mongo.get_database(namespace.database)
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
    run_task: asyncio.Task[ProjectionStatus] | None = None
    task_error: BaseException | None = None
    cleanup_errors: list[str] = []
    try:
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

        async def stream_is_ready() -> bool | None:
            return True if stream_ready.is_set() else None

        await poll_until(
            f"Mongo change-stream readiness namespace={namespace.suffix}",
            stream_is_ready,
            timeout_seconds=5,
            observe=lambda _: {"ready": stream_ready.is_set()},
        )
        await events.insert_one(event_to_document(event))

        stored = await poll_until(
            f"Mongo change-stream checkpoint namespace={namespace.suffix}",
            lambda: checkpoint.load(projector_name),
            observe=lambda _: {"checkpoint": "absent"},
        )
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
    finally:
        if run_task is not None:
            if not run_task.done():
                run_task.cancel()
            result = (await asyncio.gather(run_task, return_exceptions=True))[0]
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                task_error = result
        for index in (alias, target):
            try:
                await delete_es_index(es, index)
            except (ConnectionError, OSError, TransportError) as error:
                cleanup_errors.append(f"elasticsearch:{type(error).__name__}")
        try:
            try:
                await drop_database(mongo, database)
            except (ConnectionError, OSError, PyMongoError) as error:
                cleanup_errors.append(f"mongo:{type(error).__name__}")
        finally:
            try:
                await es.close()
            except (ConnectionError, OSError, RuntimeError, TransportError) as error:
                cleanup_errors.append(f"elasticsearch:close:{type(error).__name__}")
            finally:
                try:
                    await mongo.close()
                except (ConnectionError, OSError, RuntimeError, PyMongoError):
                    pass
        if task_error is not None and sys.exc_info()[0] is None:
            raise task_error
        if cleanup_errors and sys.exc_info()[0] is None:
            pytest.fail(f"integration cleanup failed: {', '.join(cleanup_errors)}")
