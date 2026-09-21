"""Real Mongo persistence-worker idempotency coverage."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pymongo import AsyncMongoClient

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.queue import InProcessQueue
from event_platform.storage.mongo import MongoEventStore
from event_platform.worker import PersistenceWorker
from tests.integration.support import drop_database, new_namespace, require_mongo

pytestmark = pytest.mark.integration


def _event() -> CanonicalEvent:
    value = EventInput.model_validate(
        {
            "event_type": "pageview",
            "timestamp": "2026-01-02T03:04:05Z",
            "user_id": "integration-user",
            "source_url": "https://example.test/page",
            "metadata": {"source": "worker"},
        }
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID("00000000-0000-0000-0000-000000000099"),
        ingested_at=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_real_mongo_worker_ack_and_idempotent_replay() -> None:
    uri = os.getenv("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI is not configured")
    await require_mongo(uri)
    client = AsyncMongoClient(uri)
    namespace = new_namespace()
    database = client[namespace.database]
    collection = database[f"worker_{uuid4().hex}"]
    store = MongoEventStore(collection)
    queue = InProcessQueue(capacity=2)
    value = _event()
    try:
        await store.ensure_indexes()
        await queue.send(value.model_dump(mode="json"), message_id=str(value.event_id))
        await queue.send(value.model_dump(mode="json"), message_id=f"replay-{value.event_id}")
        worker = PersistenceWorker(queue, store)
        assert await worker.process_once()
        assert await worker.process_once()
        assert worker.metrics.inserted == 1
        assert worker.metrics.duplicates == 1
        assert (await collection.count_documents({})) == 1
    finally:
        try:
            await drop_database(client, database)
        finally:
            await client.close()
