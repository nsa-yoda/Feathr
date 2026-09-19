# Implementation Plan: Realtime Statistics Cache

**Branch**: `013-realtime-stats-cache` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

## Summary

Implement a typed realtime statistics service that computes an inclusive bounded rolling-window summary from canonical Mongo aggregation, uses Redis cache-aside with versioned deterministic payloads and a short configurable TTL, coalesces same-process misses, and returns safe degraded responses when Redis is unavailable. Add the FastAPI route, optional Redis lifecycle ownership, tests, and operational documentation.

## Technical Context

**Language/Version**: Python 3.12+ with async I/O
**Primary Dependencies**: FastAPI, Pydantic v2, PyMongo Async, redis asyncio client, pytest
**Storage**: MongoDB canonical events; Redis disposable cache
**Testing**: pytest unit/failure tests; real MongoDB and Redis integration lifecycle
**Target Platform**: Single-process FastAPI service in Docker Compose
**Project Type**: Async web service
**Performance Goals**: Cache hits avoid Mongo; same-process concurrent misses perform one aggregation; TTL defaults to 10 seconds
**Constraints**: window 1..60 minutes; bounded type cardinality; no raw event metadata in cache/response; Redis cannot be a hard dependency
**Scale/Scope**: One rolling summary endpoint and one cache adapter; no distributed lock or materialized counter subsystem

## Constitution Check

- Mongo remains canonical; Redis is disposable and never required for event acceptance.
- Async Redis and PyMongo boundaries are used; no blocking network calls.
- Cache failures are classified, structured, and observable as `BYPASS`; Mongo failures use safe 503 problem responses.
- Input, output cardinality, TTL, and single-flight state are bounded.
- Request IDs, cache outcomes, and operational degradation are logged without payloads or secrets.
- Real Mongo/Redis integration coverage is included and service-gated only when dependencies are unavailable locally.

## Design

1. `src/event_platform/cache/realtime.py` owns `RealtimeStatsResponse`, `CachePort`, Redis adapter, cache key/serialization, and single-flight service.
2. `src/event_platform/api/routes/realtime_stats.py` validates the query and translates service outcomes to the response/header/problem contract.
3. `ServiceSettings` adds bounded Redis URL, cache TTL, default window, and max type settings. Lifespan creates/closes the optional async Redis client.
4. The service calls `event_store.aggregate` with `$match` on inclusive UTC bounds, `$group` by event type, `$sort`, and a bounded result sentinel.
5. Tests use deterministic clocks and fakes for unit behavior, injected failures for failure behavior, and real Mongo/Redis for the lifecycle.

## Project Structure

```text
src/event_platform/cache/realtime.py
tests/unit/test_realtime_stats.py
tests/failure/test_realtime_stats_failure.py
tests/integration/test_realtime_stats_integration.py
src/event_platform/api/routes/realtime_stats.py
src/event_platform/core/settings.py
src/event_platform/main.py
```

## Risks and Mitigations

- Redis payload drift: schema version plus Pydantic validation makes old/corrupt entries misses.
- Stampede: lock is bounded to one service instance and performs a second cache read.
- Redis outage: cache adapter returns classified failure; Mongo result remains available.
- Type cardinality: aggregation uses a `max_types + 1` sentinel and rejects oversized results.
