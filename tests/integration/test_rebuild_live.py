from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.mapping import INDEX_MAPPING, index_name
from event_platform.search.projection import (
    ProjectionStatus,
    SearchProjector,
)
from event_platform.search.rebuild import SearchRebuilder
from event_platform.search.search import ElasticsearchSearchService, SearchQuery
from event_platform.storage.change_stream import MongoChangeStreamSource
from event_platform.storage.checkpoints import MongoProjectionCheckpointStore
from event_platform.storage.mongo import EventQuery, MongoEventStore, event_to_document
from event_platform.storage.rebuilds import MongoRebuildStore
from tests.integration.support import (
    new_namespace,
    poll_until,
    require_elasticsearch,
    require_mongo,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_rebuild_lifecycle_uses_mongo_source_and_atomic_es_swap() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")
    await require_mongo(mongo_uri, require_replica_set=True)
    await require_elasticsearch(elasticsearch_url)

    mongo = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    namespace = new_namespace()
    suffix = namespace.suffix
    database = mongo.get_database(namespace.database)
    events = database.get_collection("events")
    rebuilds = database.get_collection("rebuilds")
    locks = database.get_collection("rebuild_locks")
    old_index = index_name(f"events-old-{suffix}")
    alias = f"events-rebuild-{suffix}"
    first = CanonicalEvent.from_input(
        EventInput(
            event_type="view",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            user_id="integration-user",
            source_url="https://example.test/one",
            metadata={"term": "Café"},
        ),
        event_id=uuid4(),
        ingested_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    )
    second = CanonicalEvent.from_input(
        EventInput(
            event_type="view",
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            user_id="integration-user",
            source_url="https://example.test/two",
            metadata={"term": "Résumé"},
        ),
        event_id=uuid4(),
        ingested_at=datetime(2026, 1, 2, 0, 1, tzinfo=UTC),
    )

    class MongoSource:
        def scan(self):
            return MongoEventStore(events).query(EventQuery(limit=100))

    run_task: asyncio.Task[ProjectionStatus] | None = None
    task_error: BaseException | None = None
    cleanup_errors: list[str] = []
    try:
        await events.insert_many([event_to_document(first), event_to_document(second)])
        await es.indices.create(
            index=old_index,
            settings=INDEX_MAPPING["settings"],
            mappings=INDEX_MAPPING["mappings"],
        )
        await es.indices.put_alias(index=old_index, name=alias)
        adapter = ElasticsearchRebuildAdapter(es)
        rebuilder = SearchRebuilder(
            state=MongoRebuildStore(rebuilds, lock_collection=locks),
            search=adapter,
            source=MongoSource(),
            owner=f"integration-{suffix}",
            alias=alias,
            source_collection="events",
            batch_size=1,
        )
        result = await rebuilder.run()
        assert result.phase == "completed"
        assert result.scanned_count == result.indexed_count == 2
        assert await adapter.resolve_alias(alias) == result.target_index
        assert (await es.count(index=alias))["count"] == 2

        live = CanonicalEvent.from_input(
            EventInput(
                event_type="view",
                timestamp=datetime(2026, 1, 3, tzinfo=UTC),
                user_id="integration-user",
                source_url="https://example.test/live",
                metadata={"term": "live-term"},
            ),
            event_id=uuid4(),
            ingested_at=datetime(2026, 1, 3, 0, 1, tzinfo=UTC),
        )

        checkpoint = MongoProjectionCheckpointStore(database[namespace.checkpoint_collection])
        stream_ready = asyncio.Event()
        source = MongoChangeStreamSource(events, ready=stream_ready)
        projector_name = f"integration-live-{suffix}"
        projector = SearchProjector(
            projector=projector_name,
            checkpoint=checkpoint,
            writer=ElasticsearchProjectionWriter(es, alias=alias),
        )
        run_task = asyncio.create_task(projector.run_source(source))

        async def stream_is_ready() -> bool | None:
            return True if stream_ready.is_set() else None

        await poll_until(
            f"rebuild live change-stream readiness namespace={suffix}",
            stream_is_ready,
            timeout_seconds=5,
            observe=lambda _: {"ready": stream_ready.is_set()},
        )
        await events.insert_one(event_to_document(live))
        await es.indices.refresh(index=alias)
        search = ElasticsearchSearchService(es, alias=alias)
        prior = await search.search(SearchQuery(q="café", limit=10), request_id=uuid4())

        last_hits = 0

        async def search_live():
            nonlocal last_hits
            await es.indices.refresh(index=alias)
            page = await search.search(SearchQuery(q="live-term", limit=10), request_id=uuid4())
            last_hits = len(page.items)
            return page if any(item.event_id == live.event_id for item in page.items) else None

        current = await poll_until(
            f"rebuild live search namespace={suffix}",
            search_live,
            observe=lambda _: {"search_hits": last_hits},
        )
        assert {item.event_id for item in prior.items} == {first.event_id}
        assert [item.event_id for item in current.items] == [live.event_id]
        projector.stop()
    finally:
        if run_task is not None:
            if not run_task.done():
                run_task.cancel()
            result = (await asyncio.gather(run_task, return_exceptions=True))[0]
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                task_error = result
        try:
            await es.indices.delete(index=f"events-*{suffix}*", ignore_unavailable=True)
        except (ConnectionError, OSError, RuntimeError, TransportError) as error:
            cleanup_errors.append(f"elasticsearch:{type(error).__name__}")
        try:
            await database.drop()
        except (ConnectionError, OSError, PyMongoError) as error:
            cleanup_errors.append(f"mongo:{type(error).__name__}")
        with suppress(ConnectionError, OSError, RuntimeError, TransportError):
            await es.close()
        with suppress(ConnectionError, OSError, RuntimeError, PyMongoError):
            await mongo.close()
        if task_error is not None and sys.exc_info()[0] is None:
            raise task_error
        if cleanup_errors and sys.exc_info()[0] is None:
            pytest.fail(f"integration cleanup failed: {', '.join(cleanup_errors)}")
