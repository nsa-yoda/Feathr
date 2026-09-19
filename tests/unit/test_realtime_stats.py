from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from event_platform.cache.realtime import (
    CacheUnavailable,
    RealtimeStatsService,
    build_realtime_pipeline,
    cache_key,
)
from event_platform.main import create_app
from event_platform.storage.mongo import MongoDependencyError

pytestmark = pytest.mark.unit


FIXED_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self, documents: list[Mapping[str, object]]) -> None:
        self.documents = documents
        self.calls: list[tuple[Sequence[Mapping[str, object]], int | None]] = []

    async def aggregate(
        self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]:
        self.calls.append((pipeline, max_time_ms))
        return self.documents


class FakeCache:
    def __init__(self, value: str | bytes | None = None) -> None:
        self.value = value
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.fail_get = False
        self.fail_set = False

    async def get(self, key: str) -> str | bytes | None:
        if self.fail_get:
            from event_platform.cache.realtime import CacheUnavailable

            raise CacheUnavailable("get")
        if key in self.values:
            return self.values[key]
        return None if self.values else self.value

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if self.fail_set:
            from event_platform.cache.realtime import CacheUnavailable

            raise CacheUnavailable("set")
        self.set_calls.append((key, value, ttl_seconds))
        self.values[key] = value
        self.value = value


def documents() -> list[Mapping[str, object]]:
    return [{"_id": "pageview", "count": 2}, {"_id": "purchase", "count": 1}]


def test_realtime_pipeline_is_inclusive_bounded_and_sorted() -> None:
    start = datetime(2026, 1, 1, 11, 55, tzinfo=UTC)
    pipeline = build_realtime_pipeline(start, FIXED_NOW)
    assert pipeline[0]["$match"] == {"timestamp": {"$gte": start, "$lte": FIXED_NOW}}
    assert pipeline[1]["$group"] == {"_id": "$event_type", "count": {"$sum": 1}}
    assert pipeline[2] == {"$sort": {"_id": 1}}
    assert pipeline[3] == {"$limit": 1_001}
    assert build_realtime_pipeline(start, FIXED_NOW, max_event_types=7)[3] == {"$limit": 8}


def test_cache_key_includes_schema_and_window_parameter() -> None:
    assert cache_key(5) == "realtime-stats:v1:window-minutes:5:max-types:1000"
    assert cache_key(5) != cache_key(10)
    with pytest.raises(ValueError):
        cache_key(0)
    with pytest.raises(ValueError):
        cache_key(61)


@pytest.mark.asyncio
async def test_service_miss_then_hit_populates_deterministic_payload_and_ttl() -> None:
    store = FakeStore(documents())
    cache = FakeCache()
    service = RealtimeStatsService(store=store, cache=cache, now=lambda: FIXED_NOW)

    first, first_outcome = await service.get(window_minutes=5, request_id=UUID(int=1))
    second, second_outcome = await service.get(window_minutes=5, request_id=UUID(int=2))

    assert first_outcome == "MISS"
    assert second_outcome == "HIT"
    assert first.total_events == second.total_events == 3
    assert first.by_event_type == {"pageview": 2, "purchase": 1}
    assert second.request_id == UUID(int=2)
    assert len(store.calls) == 1
    assert cache.set_calls[0][0] == cache_key(5)
    assert cache.set_calls[0][2] == 10
    assert '"by_event_type":{"pageview":2,"purchase":1}' in cache.set_calls[0][1]


@pytest.mark.asyncio
async def test_malformed_payload_is_a_miss_and_window_bounds_are_reported() -> None:
    cache = FakeCache('{"schema_version":999,"total_events":-1}')
    store = FakeStore(documents())
    service = RealtimeStatsService(store=store, cache=cache, now=lambda: FIXED_NOW)

    result, outcome = await service.get(window_minutes=10, request_id=UUID(int=3))

    assert outcome == "MISS"
    assert result.window_start == datetime(2026, 1, 1, 11, 50, tzinfo=UTC)
    assert result.window_end == FIXED_NOW
    assert len(store.calls) == 1
    assert cache.set_calls[0][0] == cache_key(10)


@pytest.mark.asyncio
async def test_negative_group_count_and_non_utc_cache_payload_are_discarded() -> None:
    cache = FakeCache(
        '{"schema_version":1,"total_events":1,"by_event_type":{"view":-1},'
        '"generated_at":"2026-01-01T12:00:00","window_start":"2026-01-01T11:55:00Z",'
        '"window_end":"2026-01-01T12:00:00Z"}'
    )
    service = RealtimeStatsService(store=FakeStore(documents()), cache=cache, now=lambda: FIXED_NOW)

    result, outcome = await service.get(window_minutes=5, request_id=UUID(int=33))

    assert outcome == "MISS"
    assert result.total_events == 3


@pytest.mark.asyncio
async def test_cached_event_type_cardinality_uses_current_service_limit() -> None:
    cache = FakeCache(
        '{"schema_version":1,"total_events":2,"by_event_type":{"view":1,"purchase":1},'
        '"generated_at":"2026-01-01T12:00:00Z","window_start":"2026-01-01T11:55:00Z",'
        '"window_end":"2026-01-01T12:00:00Z"}'
    )
    service = RealtimeStatsService(
        store=FakeStore([{"_id": "view", "count": 1}]),
        cache=cache,
        max_event_types=1,
        now=lambda: FIXED_NOW,
    )

    _, outcome = await service.get(window_minutes=5, request_id=UUID(int=37))

    assert outcome == "MISS"


@pytest.mark.asyncio
async def test_expired_entry_is_recomputed_and_different_windows_do_not_collide() -> None:
    store = FakeStore(documents())
    cache = FakeCache()
    service = RealtimeStatsService(store=store, cache=cache, now=lambda: FIXED_NOW)

    _, first_outcome = await service.get(window_minutes=5, request_id=UUID(int=30))
    _, distinct_outcome = await service.get(window_minutes=10, request_id=UUID(int=31))
    _, retained_outcome = await service.get(window_minutes=5, request_id=UUID(int=32))

    assert (first_outcome, distinct_outcome, retained_outcome) == ("MISS", "MISS", "HIT")
    assert len(store.calls) == 2
    assert [call[0] for call in cache.set_calls] == [cache_key(5), cache_key(10)]


@pytest.mark.asyncio
async def test_expired_entry_is_recomputed() -> None:
    store = FakeStore(documents())
    cache = FakeCache()
    service = RealtimeStatsService(store=store, cache=cache, now=lambda: FIXED_NOW)

    await service.get(window_minutes=5, request_id=UUID(int=35))
    cache.values.pop(cache_key(5), None)
    cache.value = None
    _, outcome = await service.get(window_minutes=5, request_id=UUID(int=36))

    assert outcome == "MISS"
    assert len(store.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_misses_for_one_key_are_coalesced() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    second_waiting = asyncio.Event()

    class NotifyingLock(asyncio.Lock):
        def __init__(self) -> None:
            super().__init__()
            self.acquire_count = 0

        async def acquire(self) -> bool:
            self.acquire_count += 1
            if self.acquire_count == 2:
                second_waiting.set()
            return await super().acquire()

    class BlockingStore(FakeStore):
        async def aggregate(
            self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
        ) -> list[Mapping[str, object]]:
            self.calls.append((pipeline, max_time_ms))
            started.set()
            await release.wait()
            return documents()

    store = BlockingStore([])
    lock = NotifyingLock()
    service = RealtimeStatsService(
        store=store,
        cache=FakeCache(),
        now=lambda: FIXED_NOW,
        lock_factory=lambda: lock,
    )
    first = asyncio.create_task(service.get(window_minutes=5, request_id=UUID(int=4)))
    await started.wait()
    second = asyncio.create_task(service.get(window_minutes=5, request_id=UUID(int=5)))
    await second_waiting.wait()
    release.set()
    await asyncio.gather(first, second)
    assert len(store.calls) == 1


@pytest.mark.asyncio
async def test_redis_bypass_emits_safe_structured_outcome(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="event_platform.realtime_stats")
    service = RealtimeStatsService(
        store=FakeStore(documents()), cache=FailingCache(), now=lambda: FIXED_NOW
    )

    await service.get(window_minutes=5, request_id=UUID(int=34))

    assert any(
        record.__dict__.get("event") == "realtime_stats.cache_bypass"
        and record.__dict__.get("operation") == "get"
        for record in caplog.records
    )


def test_realtime_route_returns_cache_header_and_request_id() -> None:
    app = create_app()
    store = FakeStore(documents())
    cache = FakeCache()
    with TestClient(app) as client:
        app.state.event_store = store
        app.state.realtime_cache = cache
        first = client.get("/events/stats/realtime?window_minutes=5")
        second = client.get("/events/stats/realtime?window_minutes=5")
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json()["request_id"] == second.headers["X-Request-ID"]


def test_realtime_route_rejects_invalid_window_with_problem_contract() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/events/stats/realtime?window_minutes=61")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == "request_validation_failed"


def test_realtime_route_empty_window_returns_zero_counts() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = FakeStore([])
        response = client.get("/events/stats/realtime")
    assert response.status_code == 200
    assert response.json()["total_events"] == 0
    assert response.json()["by_event_type"] == {}
    assert response.headers["X-Cache"] == "BYPASS"


class FailingCache:
    async def get(self, key: str) -> str | bytes | None:
        del key
        raise CacheUnavailable("get")

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        del key, value, ttl_seconds
        raise CacheUnavailable("set")


class WriteFailCache:
    async def get(self, key: str) -> str | bytes | None:
        del key
        return None

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        del key, value, ttl_seconds
        raise CacheUnavailable("set")


def test_realtime_route_returns_200_bypass_when_redis_is_unavailable() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = FakeStore(documents())
        app.state.realtime_cache = FailingCache()
        response = client.get("/events/stats/realtime")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "BYPASS"
    assert response.json()["total_events"] == 3
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_realtime_route_returns_200_bypass_when_redis_write_fails() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = FakeStore(documents())
        app.state.realtime_cache = WriteFailCache()
        response = client.get("/events/stats/realtime")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "BYPASS"
    assert response.json()["total_events"] == 3


def test_realtime_route_rejects_event_type_cardinality_overflow() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.realtime_stats_service = RealtimeStatsService(
            store=FakeStore(documents()), cache=None, max_event_types=1, now=lambda: FIXED_NOW
        )
        response = client.get("/events/stats/realtime")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


class FailingStore(FakeStore):
    async def aggregate(
        self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]:
        del pipeline, max_time_ms
        raise MongoDependencyError("aggregate")


def test_realtime_route_maps_mongo_failure_to_safe_503() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = FailingStore([])
        response = client.get("/events/stats/realtime")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Retry-After"] == "1"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.json()["detail"] == "The request could not be completed."
    assert "aggregate" not in response.text


def test_realtime_route_maps_malformed_aggregation_to_safe_503() -> None:
    app = create_app()
    with TestClient(app) as client:
        app.state.event_store = FakeStore([{"_id": {"metadata": "hidden"}, "count": 1}])
        response = client.get("/events/stats/realtime")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "metadata" not in response.text
