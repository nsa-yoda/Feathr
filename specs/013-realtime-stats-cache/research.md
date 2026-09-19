# Feature 013 Research

## Decision: Reuse the canonical Mongo aggregation boundary

Feature 009 already exposes a typed `MongoEventStore.aggregate` boundary and safe dependency error. Feature 013 will build a narrower rolling-window pipeline grouped by `event_type`, bounded by a maximum number of types, rather than reading raw events into Python.

## Decision: Redis async adapter behind a cache port

Use the official `redis.asyncio` client behind a small `CachePort`. The route and service do not depend on Redis driver types. Redis exceptions are translated to a safe cache dependency result; they never replace Mongo as the source of truth.

## Decision: Cache identity and deterministic payload

Use a versioned key such as `realtime-stats:v1:window-minutes:{n}`. Serialize a validated response with sorted keys and compact separators. The schema version prevents old payloads from being interpreted as current data.

## Decision: Process-local single-flight

Use one bounded async lock per service instance and re-check Redis after acquiring it. This coalesces same-process misses without introducing distributed locking or unbounded task state. Redis remains disposable and a second process may compute independently.

## Decision: Rolling window and freshness

Use an injectable UTC clock. `window_end` is the request computation time and `window_start` is five (or configured valid) minutes earlier. Cache hits preserve the original generated/window timestamps so clients can see age directly.
