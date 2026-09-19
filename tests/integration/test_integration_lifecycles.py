"""Feature 019 application-level real-service lifecycle coverage."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from elastic_transport import TransportError
from elasticsearch import AsyncElasticsearch
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from redis.asyncio import Redis

from event_platform.cache.realtime import (
    RealtimeStatsService,
    RedisCache,
)
from event_platform.cache.realtime import (
    cache_key as realtime_cache_key,
)
from event_platform.core.settings import ServiceSettings
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.main import create_app
from event_platform.rate_limit.redis_bucket import RedisTokenBucket
from event_platform.search.mapping import INDEX_MAPPING, index_name
from event_platform.storage.mongo import MongoEventStore, event_to_document
from tests.integration.support import (
    IntegrationNamespace,
    new_namespace,
    poll_until,
    require_elasticsearch,
    require_env,
    require_mongo,
    require_redis,
)

pytestmark = pytest.mark.integration


def _event(
    *,
    event_id: UUID | None = None,
    event_type: str = "pageview",
    timestamp: datetime = datetime(2026, 1, 5, 12, 0, tzinfo=UTC),
    user_id: str = "feature-019-user",
    metadata: dict[str, object] | None = None,
) -> CanonicalEvent:
    value = EventInput(
        event_type=event_type,
        timestamp=timestamp,
        user_id=user_id,
        source_url="https://example.test/feature-019",
        metadata=metadata or {"source": "feature-019"},
    )
    return CanonicalEvent.from_input(
        value,
        event_id=event_id or uuid4(),
        ingested_at=timestamp + timedelta(minutes=1),
    )


async def _drop_database(uri: str, namespace: IntegrationNamespace) -> None:
    client = AsyncMongoClient(uri)
    try:
        await client.drop_database(namespace.database)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_http_ingestion_worker_and_query_use_real_mongo() -> None:
    endpoints = require_env("MONGO_URI")
    mongo_uri = endpoints["MONGO_URI"]
    await require_mongo(mongo_uri)
    namespace = new_namespace()
    setup_client = AsyncMongoClient(mongo_uri)
    try:
        await MongoEventStore(
            setup_client[namespace.database][namespace.collection]
        ).ensure_indexes()
    except (ConnectionError, OSError, PyMongoError):
        await setup_client.close()
        await _drop_database(mongo_uri, namespace)
        raise
    else:
        await setup_client.close()

    app = create_app(
        ServiceSettings(
            env="test",
            mongo_url=mongo_uri,
            mongo_database=namespace.database,
            mongo_collection=namespace.collection,
            queue_visibility_timeout=1,
        )
    )
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://integration.test"
            ) as client:
                response = await client.post(
                    "/events",
                    json={
                        "event_type": "pageview",
                        "timestamp": "2026-01-05T12:00:00Z",
                        "user_id": "feature-019-user",
                        "source_url": "https://example.test/feature-019",
                        "metadata": {"integration_term": namespace.suffix},
                    },
                )
                assert response.status_code == 202
                event_id = response.json()["event_id"]
                assert response.json()["event_id"] == str(event_id)

                async def find_event() -> dict[str, object] | None:
                    nonlocal last_status
                    page = await client.get("/events", params={"user_id": "feature-019-user"})
                    last_status = page.status_code
                    if page.status_code != 200:
                        return None
                    for item in page.json()["items"]:
                        if item["event_id"] == event_id:
                            return item
                    return None

                last_status: int | None = None
                found = await poll_until(
                    f"HTTP ingestion/query namespace={namespace.suffix}",
                    find_event,
                    observe=lambda _: {"http_status": last_status},
                )
                assert found["event_id"] == event_id
                assert found["event_type"] == "pageview"
                assert found["timestamp"] == "2026-01-05T12:00:00Z"
                assert found["user_id"] == "feature-019-user"
                assert found["source_url"] == "https://example.test/feature-019"
                assert found["metadata"] == {"integration_term": namespace.suffix}
    finally:
        await _drop_database(mongo_uri, namespace)


@pytest.mark.asyncio
async def test_http_change_stream_projection_reaches_real_search_api() -> None:
    endpoints = require_env("MONGO_URI", "ELASTICSEARCH_URL")
    mongo_uri = endpoints["MONGO_URI"]
    elasticsearch_url = endpoints["ELASTICSEARCH_URL"]
    await require_mongo(mongo_uri, require_replica_set=True)
    await require_elasticsearch(elasticsearch_url)
    namespace = new_namespace()
    physical = index_name(f"events-it-physical-{namespace.suffix}")
    setup_es = AsyncElasticsearch(hosts=[elasticsearch_url])
    try:
        await setup_es.indices.create(
            index=physical,
            settings=INDEX_MAPPING["settings"],
            mappings=INDEX_MAPPING["mappings"],
        )
        await setup_es.indices.put_alias(index=physical, name=namespace.alias)
    except (ConnectionError, OSError, RuntimeError, TransportError) as error:
        await setup_es.close()
        cleanup_es = AsyncElasticsearch(hosts=[elasticsearch_url])
        try:
            try:
                await cleanup_es.indices.delete_alias(
                    index=physical, name=namespace.alias, ignore_unavailable=True
                )
                await cleanup_es.indices.delete(index=f"{physical}*", ignore_unavailable=True)
            except (ConnectionError, OSError, RuntimeError, TransportError):
                pass
        finally:
            await cleanup_es.close()
            await _drop_database(mongo_uri, namespace)
        raise error
    else:
        await setup_es.close()

    app = create_app(
        ServiceSettings(
            env="test",
            mongo_url=mongo_uri,
            mongo_database=namespace.database,
            mongo_collection=namespace.collection,
            elasticsearch_url=elasticsearch_url,
            elasticsearch_alias=namespace.alias,
        )
    )
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://integration.test"
            ) as client:
                response = await client.post(
                    "/events",
                    json={
                        "event_type": "pageview",
                        "timestamp": "2026-01-05T12:00:00Z",
                        "user_id": "feature-019-search",
                        "source_url": "https://example.test/search",
                        "metadata": {"integration_term": namespace.suffix},
                    },
                )
                assert response.status_code == 202
                event_id = response.json()["event_id"]

                async def search_event() -> dict[str, object] | None:
                    nonlocal last_status
                    result = await client.get(
                        "/events/search", params={"q": namespace.suffix, "limit": 10}
                    )
                    last_status = result.status_code
                    if result.status_code != 200:
                        return None
                    return next(
                        (item for item in result.json()["items"] if item["event_id"] == event_id),
                        None,
                    )

                last_status: int | None = None
                found = await poll_until(
                    f"Mongo change stream to HTTP search namespace={namespace.suffix}",
                    search_event,
                    observe=lambda _: {"http_status": last_status},
                )
                assert found["event_id"] == event_id
    finally:
        cleanup_errors: list[str] = []
        cleanup_es = AsyncElasticsearch(hosts=[elasticsearch_url])
        try:
            try:
                await cleanup_es.indices.delete_alias(
                    index=physical, name=namespace.alias, ignore_unavailable=True
                )
                await cleanup_es.indices.delete(index=f"{physical}*", ignore_unavailable=True)
            except (ConnectionError, OSError, RuntimeError, TransportError) as error:
                cleanup_errors.append(f"elasticsearch:{type(error).__name__}")
        finally:
            try:
                await cleanup_es.close()
            finally:
                await _drop_database(mongo_uri, namespace)
        if cleanup_errors and sys.exc_info()[0] is None:
            pytest.fail(f"integration cleanup failed: {', '.join(cleanup_errors)}")


@pytest.mark.asyncio
async def test_http_analytics_and_realtime_cache_use_real_services() -> None:
    endpoints = require_env("MONGO_URI", "REDIS_URL")
    mongo_uri = endpoints["MONGO_URI"]
    redis_url = endpoints["REDIS_URL"]
    await require_mongo(mongo_uri)
    await require_redis(redis_url)
    namespace = new_namespace()
    mongo = AsyncMongoClient(mongo_uri)
    redis = Redis.from_url(redis_url)
    events = mongo[namespace.database][namespace.collection]
    first = _event(event_type="purchase", timestamp=datetime(2026, 1, 5, 12, 5, tzinfo=UTC))
    second = _event(event_type="pageview", timestamp=datetime(2026, 1, 5, 12, 15, tzinfo=UTC))
    cache_prefix = f"feature019-{namespace.suffix}"
    cache_key = f"{cache_prefix}:{realtime_cache_key(5)}"
    try:
        await events.insert_many([event_to_document(first), event_to_document(second)])
        await redis.delete(cache_key)
        app = create_app(
            ServiceSettings(
                env="test",
                mongo_url=mongo_uri,
                mongo_database=namespace.database,
                mongo_collection=namespace.collection,
                redis_url=redis_url,
                realtime_cache_ttl_seconds=10,
            )
        )
        async with app.router.lifespan_context(app):
            app.state.rate_limiter.redis_bucket = RedisTokenBucket(
                redis, key_prefix=f"{cache_prefix}:"
            )
            app.state.realtime_stats_service = RealtimeStatsService(
                store=app.state.event_store,
                cache=RedisCache(redis, key_prefix=cache_prefix),
                ttl_seconds=10,
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://integration.test"
            ) as client:
                stats = await client.get(
                    "/events/stats",
                    params={
                        "bucket": "hour",
                        "start": "2026-01-05T12:00:00Z",
                        "end": "2026-01-05T12:59:59Z",
                    },
                )
                assert stats.status_code == 200
                assert sum(point["count"] for point in stats.json()["points"]) == 2
                first_cache = await client.get(
                    "/events/stats/realtime", params={"window_minutes": 5}
                )
                second_cache = await client.get(
                    "/events/stats/realtime", params={"window_minutes": 5}
                )
                assert first_cache.status_code == second_cache.status_code == 200
                assert first_cache.headers["x-cache"] == "MISS"
                assert second_cache.headers["x-cache"] == "HIT"
                assert (
                    first_cache.json()["total_events"] == second_cache.json()["total_events"] == 2
                )
                assert 1 <= await redis.ttl(cache_key) <= 10
    finally:
        try:
            keys = [key async for key in redis.scan_iter(match=f"{cache_prefix}:*")]
            if keys:
                await redis.delete(*keys)
        finally:
            try:
                await redis.aclose()
            finally:
                try:
                    await mongo.drop_database(namespace.database)
                finally:
                    await mongo.close()
