from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from event_platform.cache.realtime import RealtimeStatsService, RedisCache, cache_key
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.storage.mongo import MongoEventStore, event_to_document

pytestmark = pytest.mark.integration


def make_event(event_type: str, minute: int) -> CanonicalEvent:
    timestamp = datetime(2026, 1, 1, 12, minute, tzinfo=UTC)
    return CanonicalEvent.from_input(
        EventInput(
            event_type=event_type,
            timestamp=timestamp,
            user_id="realtime-integration",
            source_url=f"https://example.test/{event_type}/{minute}",
            metadata={"source": "feature013"},
        ),
        event_id=uuid4(),
        ingested_at=timestamp,
    )


@pytest.mark.asyncio
async def test_real_mongo_redis_realtime_cache_miss_hit_lifecycle() -> None:
    mongo_uri = os.getenv("MONGO_URI")
    redis_url = os.getenv("REDIS_URL")
    if not mongo_uri or not redis_url:
        pytest.skip("MONGO_URI and REDIS_URL are required")
    mongo = AsyncMongoClient(mongo_uri)
    redis = Redis.from_url(redis_url)
    suffix = uuid4().hex[:10]
    database = mongo.get_database(f"event_platform_realtime_{suffix}")
    events = database.get_collection("events")
    try:
        try:
            await mongo.admin.command("ping")
            await redis.ping()
        except (ConnectionError, OSError, PyMongoError, RedisError) as error:
            pytest.skip(f"integration services unavailable: {type(error).__name__}")
        first = make_event("view", 57)
        second = make_event("purchase", 58)
        outside = make_event("view", 40)
        await events.insert_many(
            [event_to_document(first), event_to_document(second), event_to_document(outside)]
        )
        service = RealtimeStatsService(
            store=MongoEventStore(events),
            cache=RedisCache(redis, key_prefix=f"feature013-{suffix}"),
            ttl_seconds=10,
            now=lambda: datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
        )
        first_result, first_outcome = await service.get(window_minutes=5, request_id=UUID(int=1))
        second_result, second_outcome = await service.get(window_minutes=5, request_id=UUID(int=2))
        assert first_outcome == "MISS"
        assert second_outcome == "HIT"
        assert first_result.total_events == second_result.total_events == 2
        assert first_result.by_event_type == {"purchase": 1, "view": 1}
        assert second_result.request_id == UUID(int=2)
        namespaced_key = f"feature013-{suffix}:{cache_key(5)}"
        assert await redis.exists(namespaced_key)
        assert 1 <= await redis.ttl(namespaced_key) <= 10
    finally:
        try:
            await redis.delete(f"feature013-{suffix}:{cache_key(5)}")
        except (ConnectionError, OSError, RedisError):
            pass
        try:
            await database.drop()
        except (ConnectionError, OSError, PyMongoError):
            pass
        await redis.aclose()
        await mongo.close()
