"""Cache-aside realtime statistics over canonical MongoDB event state."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from redis.asyncio import Redis
from redis.exceptions import RedisError

from event_platform.observability.metrics import MetricsRegistry
from event_platform.storage.mongo import MongoDependencyError

logger = logging.getLogger("event_platform.realtime_stats")

SCHEMA_VERSION: Literal[1] = 1
DEFAULT_WINDOW_MINUTES = 5
MIN_WINDOW_MINUTES = 1
MAX_WINDOW_MINUTES = 60
DEFAULT_TTL_SECONDS = 10
MAX_EVENT_TYPES = 1_000
MAX_AGGREGATION_TIME_MS = 5_000


class CacheUnavailable(RuntimeError):
    """A cache operation failed and the caller should use canonical state."""

    def __init__(self, operation: str) -> None:
        super().__init__(operation)
        self.operation = operation


class RealtimeStatsResultLimit(ValueError):
    """The canonical result exceeded the bounded event-type cardinality."""


class CachePort(Protocol):
    async def get(self, key: str) -> str | bytes | None: ...

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...


class AggregateStore(Protocol):
    async def aggregate(
        self, pipeline: Sequence[Mapping[str, object]], *, max_time_ms: int | None = None
    ) -> list[Mapping[str, object]]: ...


class RedisCache(CachePort):
    """Translate Redis driver failures into a safe cache boundary."""

    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str = "",
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if len(key_prefix) > 64 or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in key_prefix
        ):
            raise ValueError("cache key prefix is invalid")
        self._client = client
        self._key_prefix = key_prefix
        self._metrics = metrics

    def _key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}" if self._key_prefix else key

    async def get(self, key: str) -> str | bytes | None:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            value = cast(str | bytes | None, await self._client.get(self._key(key)))
            outcome = "success"
            return value
        except (RedisError, OSError, TimeoutError):
            raise CacheUnavailable("get") from None
        finally:
            self._record_operation("get_cache", outcome, started_at)

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            await self._client.set(self._key(key), value, ex=ttl_seconds)
            outcome = "success"
        except (RedisError, OSError, TimeoutError):
            raise CacheUnavailable("set") from None
        finally:
            self._record_operation("set_cache", outcome, started_at)

    def _record_operation(self, operation: str, outcome: str, started_at: float) -> None:
        if self._metrics is None:
            return
        self._metrics.observe_histogram(
            "event_platform_redis_operation_latency_seconds",
            max(0.0, time.perf_counter() - started_at),
            {"operation": operation},
        )
        self._metrics.inc(
            "event_platform_redis_operations_total",
            {"operation": operation, "outcome": outcome},
        )


class RealtimeStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    total_events: int = Field(ge=0)
    by_event_type: dict[str, int]
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    request_id: UUID

    @model_validator(mode="after")
    def validate_counts_and_timestamps(self) -> RealtimeStatsResponse:
        _validate_counts(self.by_event_type, self.total_events)
        _validate_utc(self.generated_at, self.window_start, self.window_end)
        _validate_temporal_relationships(
            generated_at=self.generated_at,
            window_start=self.window_start,
            window_end=self.window_end,
        )
        return self


class _CachedStats(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    total_events: int = Field(ge=0)
    by_event_type: dict[str, int]
    generated_at: datetime
    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_counts_and_timestamps(self) -> _CachedStats:
        _validate_counts(self.by_event_type, self.total_events)
        _validate_utc(self.generated_at, self.window_start, self.window_end)
        _validate_temporal_relationships(
            generated_at=self.generated_at,
            window_start=self.window_start,
            window_end=self.window_end,
        )
        return self


def _validate_counts(by_event_type: Mapping[str, int], total_events: int) -> None:
    if len(by_event_type) > MAX_EVENT_TYPES:
        raise ValueError("realtime statistics event-type cardinality is invalid")
    if any(
        not 1 <= len(event_type) <= 128 or isinstance(count, bool) or count < 1
        for event_type, count in by_event_type.items()
    ):
        raise ValueError("realtime statistics counts are invalid")
    if sum(by_event_type.values()) != total_events:
        raise ValueError("realtime statistics total does not match grouped counts")


def _validate_utc(*values: datetime) -> None:
    if any(value.tzinfo is None or value.utcoffset() != timedelta(0) for value in values):
        raise ValueError("realtime statistics timestamps must be UTC")


def _validate_temporal_relationships(
    *, generated_at: datetime, window_start: datetime, window_end: datetime
) -> None:
    if window_start > window_end or generated_at < window_end:
        raise ValueError("realtime statistics timestamps are out of order")


def cache_key(window_minutes: int, *, max_event_types: int = MAX_EVENT_TYPES) -> str:
    """Build a stable key containing every current result-affecting parameter."""

    if not MIN_WINDOW_MINUTES <= window_minutes <= MAX_WINDOW_MINUTES:
        raise ValueError("window_minutes is outside the supported range")
    if not 1 <= max_event_types <= MAX_EVENT_TYPES:
        raise ValueError("max_event_types is outside the supported range")
    return (
        f"realtime-stats:v{SCHEMA_VERSION}:window-minutes:{window_minutes}"
        f":max-types:{max_event_types}"
    )


def build_realtime_pipeline(
    window_start: datetime,
    window_end: datetime,
    *,
    max_event_types: int = MAX_EVENT_TYPES,
) -> list[dict[str, object]]:
    """Build a bounded inclusive aggregation over canonical event timestamps."""

    if not 1 <= max_event_types <= MAX_EVENT_TYPES:
        raise ValueError("max_event_types is outside the supported range")

    return [
        {
            "$match": {
                "timestamp": {"$gte": window_start, "$lte": window_end},
            }
        },
        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$limit": max_event_types + 1},
    ]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class RealtimeStatsService:
    """Coordinate Redis cache-aside reads and canonical Mongo computation."""

    def __init__(
        self,
        *,
        store: AggregateStore,
        cache: CachePort | None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_event_types: int = MAX_EVENT_TYPES,
        now: Callable[[], datetime] = _utc_now,
        lock_factory: Callable[[], asyncio.Lock] = asyncio.Lock,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not 1 <= ttl_seconds <= 300:
            raise ValueError("realtime cache TTL is outside the supported range")
        if not 1 <= max_event_types <= MAX_EVENT_TYPES:
            raise ValueError("realtime event-type limit is outside the supported range")
        self._store = store
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._max_event_types = max_event_types
        self._now = now
        self._lock_factory = lock_factory
        self._metrics = metrics
        self._locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Task[tuple[RealtimeStatsResponse, str]]] = {}

    async def get(
        self, *, window_minutes: int, request_id: UUID
    ) -> tuple[RealtimeStatsResponse, str]:
        if not MIN_WINDOW_MINUTES <= window_minutes <= MAX_WINDOW_MINUTES:
            raise ValueError("window_minutes is outside the supported range")
        key = cache_key(window_minutes, max_event_types=self._max_event_types)
        cached, cache_available = await self._read_cache(key, request_id=request_id)
        if cached is not None:
            self._emit_outcome("HIT", request_id)
            self._record_cache_outcome("hit")
            return _response_from_cached(cached, request_id), "HIT"

        lock = self._locks.setdefault(key, self._lock_factory())
        async with lock:
            cached, second_cache_available = await self._read_cache(key, request_id=request_id)
            cache_available = cache_available and second_cache_available
            if cached is not None:
                self._emit_outcome("HIT", request_id)
                self._record_cache_outcome("hit")
                return _response_from_cached(cached, request_id), "HIT"
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(
                    self._compute_and_store(
                        key=key,
                        window_minutes=window_minutes,
                        request_id=request_id,
                        cache_available=cache_available,
                    )
                )
                self._inflight[key] = task
        try:
            # A cancelled waiter must not cancel shared work needed by other callers.
            response, outcome = await asyncio.shield(task)
        finally:
            if task.done() and self._inflight.get(key) is task:
                self._inflight.pop(key, None)
        response = response.model_copy(update={"request_id": request_id})
        if outcome == "BYPASS":
            self._emit_bypass(request_id=request_id)
            self._record_cache_outcome("bypass")
        else:
            self._emit_outcome(outcome, request_id)
            self._record_cache_outcome("miss" if outcome == "MISS" else "bypass")
        return response, outcome

    async def _compute_and_store(
        self,
        *,
        key: str,
        window_minutes: int,
        request_id: UUID,
        cache_available: bool,
    ) -> tuple[RealtimeStatsResponse, str]:
        response = await self._compute(window_minutes=window_minutes, request_id=request_id)
        if self._cache is None or not cache_available:
            return response, "BYPASS"
        try:
            await self._cache.set(
                key,
                _serialize(response),
                ttl_seconds=self._ttl_seconds,
            )
        except CacheUnavailable:
            return response, "BYPASS"
        return response, "MISS"

    async def _read_cache(self, key: str, *, request_id: UUID) -> tuple[_CachedStats | None, bool]:
        if self._cache is None:
            return None, False
        try:
            raw = await self._cache.get(key)
        except CacheUnavailable as error:
            self._emit_bypass(error.operation, request_id)
            return None, False
        if raw is None:
            return None, True
        try:
            value = _CachedStats.model_validate_json(raw)
            if value.schema_version != SCHEMA_VERSION:
                raise ValueError("cache schema version is unsupported")
            if len(value.by_event_type) > self._max_event_types:
                raise ValueError("cache event-type cardinality exceeds configured limit")
            return value, True
        except (TypeError, ValueError, ValidationError, UnicodeDecodeError):
            logger.info(
                "realtime stats cache entry discarded",
                extra={"event": "realtime_stats.cache_invalid", "request_id": str(request_id)},
            )
            return None, True

    async def _compute(self, *, window_minutes: int, request_id: UUID) -> RealtimeStatsResponse:
        clock_value = self._now()
        try:
            _validate_utc(clock_value)
        except ValueError as error:
            raise MongoDependencyError("clock_invalid") from error
        window_end = clock_value.astimezone(UTC).replace(microsecond=0)
        window_start = window_end - timedelta(minutes=window_minutes)
        documents = await self._store.aggregate(
            build_realtime_pipeline(
                window_start, window_end, max_event_types=self._max_event_types
            ),
            max_time_ms=MAX_AGGREGATION_TIME_MS,
        )
        if len(documents) > self._max_event_types:
            raise RealtimeStatsResultLimit("realtime statistics exceed event-type limit")
        by_event_type: dict[str, int] = {}
        for document in documents:
            if not isinstance(document, Mapping):
                raise MongoDependencyError("decode_realtime_stats")
            event_type = document.get("_id")
            count = document.get("count")
            if not isinstance(event_type, str) or not 1 <= len(event_type) <= 128:
                raise MongoDependencyError("decode_realtime_stats")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise MongoDependencyError("decode_realtime_stats")
            if event_type in by_event_type:
                raise MongoDependencyError("decode_realtime_stats")
            by_event_type[event_type] = count
        return RealtimeStatsResponse(
            total_events=sum(by_event_type.values()),
            by_event_type=dict(sorted(by_event_type.items())),
            generated_at=window_end,
            window_start=window_start,
            window_end=window_end,
            request_id=request_id,
        )

    @staticmethod
    def _emit_bypass(operation: str = "unconfigured", request_id: UUID | None = None) -> None:
        logger.info(
            "realtime stats cache bypass",
            extra={
                "event": "realtime_stats.cache_bypass",
                "operation": operation,
                "request_id": str(request_id) if request_id is not None else None,
            },
        )

    def _record_cache_outcome(self, outcome: str) -> None:
        if self._metrics is not None:
            self._metrics.increment_cache(outcome)

    @staticmethod
    def _emit_outcome(outcome: str, request_id: UUID) -> None:
        logger.info(
            "realtime stats cache outcome",
            extra={
                "event": f"realtime_stats.cache_{outcome.lower()}",
                "outcome": outcome,
                "request_id": str(request_id),
            },
        )


def _serialize(response: RealtimeStatsResponse) -> str:
    cached = _CachedStats.model_validate(response.model_dump(exclude={"request_id"}))
    return json.dumps(cached.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _response_from_cached(cached: _CachedStats, request_id: UUID) -> RealtimeStatsResponse:
    return RealtimeStatsResponse(**cached.model_dump(), request_id=request_id)
