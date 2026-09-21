"""Real MongoDB coverage for Feature 003, enabled with MONGO_URI."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pymongo import AsyncMongoClient

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.storage.mongo import EventAlreadyExists, EventQuery, MongoEventStore
from tests.integration.support import drop_database, new_namespace, require_mongo

pytestmark = pytest.mark.integration


def _event(
    event_id: UUID,
    timestamp: datetime,
    *,
    event_type: str = "pageview",
    user_id: str = "integration-user",
    source_url: str = "https://example.test/integration",
) -> CanonicalEvent:
    input_event = EventInput.model_validate(
        {
            "event_type": event_type,
            "timestamp": timestamp.isoformat(),
            "user_id": user_id,
            "source_url": source_url,
            "metadata": {"source": "integration"},
        }
    )
    return CanonicalEvent.from_input(input_event, event_id=event_id, ingested_at=timestamp)


@pytest.mark.asyncio
async def test_real_mongo_indexes_uniqueness_fetch_and_ordering() -> None:
    uri = os.getenv("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI is not configured")
    await require_mongo(uri)

    client = AsyncMongoClient(uri)
    namespace = new_namespace()
    database = client[namespace.database]
    collection = database[f"events_{uuid4().hex}"]
    store = MongoEventStore(collection)
    try:
        first_names = await store.ensure_indexes()
        assert await store.ensure_indexes() == first_names
        first_id = UUID("00000000-0000-0000-0000-000000000001")
        second_id = UUID("00000000-0000-0000-0000-000000000002")
        third_id = UUID("00000000-0000-0000-0000-000000000003")
        timestamp = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
        await store.insert(_event(first_id, timestamp))
        await store.insert(_event(second_id, timestamp))
        await store.insert(
            _event(
                third_id,
                timestamp + timedelta(seconds=1),
                event_type="signup",
                user_id="other-user",
                source_url="https://example.test/other",
            )
        )
        with pytest.raises(EventAlreadyExists):
            await store.insert(_event(first_id, timestamp))
        assert await store.get_by_id(first_id) is not None
        page = [item async for item in store.query(EventQuery(limit=1))]
        assert len(page) == 1
        next_page = [
            item
            async for item in store.query(
                EventQuery(
                    limit=1,
                    after_timestamp=page[0].timestamp,
                    after_event_id=page[0].event_id,
                )
            )
        ]
        assert [item.event_id for item in next_page] == [second_id]
        final_page = [
            item
            async for item in store.query(
                EventQuery(
                    limit=1,
                    after_timestamp=next_page[0].timestamp,
                    after_event_id=next_page[0].event_id,
                )
            )
        ]
        assert [item.event_id for item in final_page] == [first_id]
        assert [item.event_id async for item in store.query(EventQuery(event_type="signup"))] == [
            third_id
        ]
        assert [item.event_id async for item in store.query(EventQuery(user_id="other-user"))] == [
            third_id
        ]
        assert [
            item.event_id
            async for item in store.query(EventQuery(source_url="https://example.test/other"))
        ] == [third_id]
        bounded = [
            item
            async for item in store.query(
                EventQuery(timestamp_from=timestamp, timestamp_to=timestamp)
            )
        ]
        assert {item.event_id for item in bounded} == {first_id, second_id}
        aggregation = await store.aggregate([{"$count": "count"}])
        assert aggregation == [{"count": 3}]
        index_documents = await (await collection.list_indexes()).to_list(length=None)
        assert {item["name"] for item in index_documents} == {
            "_id_",
            "uq_events_event_id",
            "ix_events_timestamp_event_id",
            "ix_events_event_type_timestamp_event_id",
            "ix_events_user_id_timestamp_event_id",
            "ix_events_source_url_timestamp_event_id",
        }
        definitions = {item["name"]: item for item in index_documents}
        assert definitions["uq_events_event_id"]["key"] == {"event_id": 1}
        assert definitions["uq_events_event_id"]["unique"] is True
        assert definitions["ix_events_timestamp_event_id"]["key"] == {
            "timestamp": -1,
            "event_id": -1,
        }
        assert definitions["ix_events_event_type_timestamp_event_id"]["key"] == {
            "event_type": 1,
            "timestamp": -1,
            "event_id": -1,
        }
    finally:
        try:
            await drop_database(client, database)
        finally:
            await client.close()
