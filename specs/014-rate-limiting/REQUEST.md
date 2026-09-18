# Feature Request: Mandatory Rate Limiting

## Intent

Rate limiting is a required system feature, not optional bonus work.

## Primary algorithm

Atomic Redis-backed token bucket implemented with Lua or equivalent single atomic execution. Support configurable capacity/refill per route class.

Suggested route classes to clarify:

- ingestion write;
- normal read/query;
- search/analytics expensive read;
- ops/status;
- health/metrics exempt or separately controlled.

## Client identity

In this unauthenticated assessment, default to direct peer IP. Do not trust `X-Forwarded-For` unless `TRUSTED_PROXY_HOPS`/equivalent is explicitly configured and parsing is tested.

## Redis degradation

If Redis cannot be used, activate a conservative in-process token bucket keyed by the same normalized identity+route class. Emit a rate-limiter degraded state. This prevents both fail-open abuse and fail-closed full outage.

## Response

429 problem document plus `Retry-After`. Include useful standard/de-facto limit headers consistently without exposing internal keys.

## Memory safety

Local fallback limiter must evict idle keys / cap memory; untrusted IPs cannot create an unbounded dictionary forever.

## Tests

Allow/refill/deny math, atomic Redis behavior integration, independent route classes, fallback activation, fallback eviction, spoofed forwarding header ignored by default, retry header correctness.


## Dependencies

001

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
