from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.cache.realtime import CacheUnavailable, RealtimeStatsService
from event_platform.storage.mongo import MongoDependencyError

pytestmark = pytest.mark.failure


class Store:
    def __init__(self, documents: list[Mapping[str, object]]) -> None:
        self.documents = documents

    async def aggregate(
        self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]:
        del pipeline, max_time_ms
        return self.documents


class DownCache:
    async def get(self, key: str) -> str | bytes | None:
        del key
        raise CacheUnavailable("get")

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        del key, value, ttl_seconds
        raise CacheUnavailable("set")


class BadStore(Store):
    async def aggregate(
        self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]:
        del pipeline, max_time_ms
        raise MongoDependencyError("aggregate")


@pytest.mark.asyncio
async def test_redis_failure_bypasses_cache_and_returns_mongo_result() -> None:
    service = RealtimeStatsService(
        store=Store([{"_id": "view", "count": 1}]),
        cache=DownCache(),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    result, outcome = await service.get(window_minutes=5, request_id=UUID(int=1))

    assert outcome == "BYPASS"
    assert result.total_events == 1


@pytest.mark.asyncio
async def test_mongo_failure_is_not_hidden_by_cache_layer() -> None:
    service = RealtimeStatsService(
        store=BadStore([]),
        cache=DownCache(),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(MongoDependencyError):
        await service.get(window_minutes=5, request_id=UUID(int=2))


@pytest.mark.asyncio
async def test_invalid_aggregation_document_is_classified_as_dependency_failure() -> None:
    service = RealtimeStatsService(
        store=Store([{"_id": {"secret": "no"}, "count": 1}]),
        cache=None,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )

    with pytest.raises(MongoDependencyError):
        await service.get(window_minutes=5, request_id=UUID(int=3))


@pytest.mark.asyncio
async def test_non_mapping_and_duplicate_aggregation_documents_are_classified() -> None:
    for documents in (
        ["not-a-document"],
        [{"_id": "view", "count": 1}, {"_id": "view", "count": 2}],
    ):
        service = RealtimeStatsService(
            store=Store(documents),  # type: ignore[arg-type]
            cache=None,
            now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )
        with pytest.raises(MongoDependencyError):
            await service.get(window_minutes=5, request_id=UUID(int=4))


@pytest.mark.asyncio
async def test_naive_clock_is_classified_as_dependency_failure() -> None:
    service = RealtimeStatsService(
        store=Store([]),
        cache=None,
        now=lambda: datetime(2026, 1, 1),
    )

    with pytest.raises(MongoDependencyError):
        await service.get(window_minutes=5, request_id=UUID(int=5))


@pytest.mark.asyncio
async def test_redis_failure_still_coalesces_concurrent_mongo_computation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingStore(Store):
        def __init__(self) -> None:
            super().__init__([{"_id": "view", "count": 1}])
            self.calls = 0

        async def aggregate(
            self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
        ) -> list[Mapping[str, object]]:
            self.calls += 1
            started.set()
            await release.wait()
            return await super().aggregate(pipeline, max_time_ms=max_time_ms)

    store = BlockingStore()
    service = RealtimeStatsService(
        store=store,
        cache=DownCache(),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    first = asyncio.create_task(service.get(window_minutes=5, request_id=UUID(int=6)))
    await started.wait()
    second = asyncio.create_task(service.get(window_minutes=5, request_id=UUID(int=7)))
    release.set()
    outcomes = await asyncio.gather(first, second)

    assert store.calls == 1
    assert [outcome for _, outcome in outcomes] == ["BYPASS", "BYPASS"]
