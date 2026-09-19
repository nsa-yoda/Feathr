from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.mapping import INDEX_MAPPING, index_name
from event_platform.search.rebuild import SearchRebuilder
from event_platform.storage.mongo import EventQuery, MongoEventStore, event_to_document
from event_platform.storage.rebuilds import MongoRebuildStore

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_rebuild_lifecycle_uses_mongo_source_and_atomic_es_swap() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    elasticsearch_url = os.getenv("ELASTICSEARCH_URL")
    if not mongo_uri or not elasticsearch_url:
        pytest.skip("MONGO_URI and ELASTICSEARCH_URL are required")

    mongo = AsyncMongoClient(mongo_uri)
    es = AsyncElasticsearch(hosts=[elasticsearch_url])
    suffix = uuid4().hex[:10]
    database = mongo.get_database(f"event_platform_rebuild_{suffix}")
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

    try:
        try:
            await mongo.admin.command("ping")
            await es.info()
        except (ConnectionError, OSError, RuntimeError, PyMongoError, TransportError) as error:
            pytest.skip(f"integration services unavailable: {type(error).__name__}")
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
    finally:
        try:
            await es.indices.delete(index=f"events-*{suffix}*", ignore_unavailable=True)
        except Exception:
            pass
        await database.drop()
        await es.close()
        await mongo.close()
