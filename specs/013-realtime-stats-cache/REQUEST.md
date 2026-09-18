# Feature Request: Realtime Statistics Cache

## Endpoint

`GET /events/stats/realtime`

## Summary definition

Define a lightweight rolling window (target 5 minutes by default, configurable with a bounded allowed set/range) returning total events and counts by event type plus `generated_at`, `window_start`, `window_end`.

## Cache

Redis cache-aside with configurable default TTL near 10 seconds. Key includes schema/version and parameters that affect the result. Encode response deterministically.

## Observable response

Set `X-Cache: HIT`, `MISS`, or `BYPASS`. Cache entry age/generated timestamp should make staleness understandable.

## Redis failure

Compute against Mongo, return 200 if Mongo succeeds, emit bypass/degraded metrics/logs. Redis cannot make the endpoint unavailable by itself.

## Stampede behavior

Use modest request coalescing/single-flight where practical; do not build a large distributed locking subsystem just for this take-home.

## Tests

Miss then hit, TTL expiry, key correctness, Redis unavailable bypass, Mongo error mapping, no stale cross-parameter collision.


## Dependencies

003, 009

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
