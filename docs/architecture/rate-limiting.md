# Rate Limiting Design Details

## Leaky bucket state

Per `(route_class, client_identity)` store the next available release slot. Redis execution atomically reserves slots at the configured leak interval. Requests within the bounded backlog wait asynchronously until their slot; only a full backlog is rejected. State has a bounded expiry and returns delay, remaining queue capacity, and retry metadata.

## Route costs

Keep costs simple and documented. Search/analytics may have stricter capacities than cheap canonical reads. Do not create per-URL path-cardinality keys from arbitrary IDs; classify by route template.

## Local fallback

Use the same leaky-bucket reservation semantics with intentionally stricter capacity/leak rate. Store entries in a bounded TTL/LRU-like structure so hostile unique IPs cannot leak memory indefinitely.

## Proxy identity

By default identity is socket peer address. Only when trusted proxy hops are configured should forwarded chain parsing choose the client address. Malformed chains fall back safely and are never trusted more broadly than configured.

## Response headers

Queued responses include `X-RateLimit-Queued: true`. Define and test consistent `Retry-After` for full-backlog overflow; include `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset`. Never include raw Redis keys.

The implementation is split between `src/event_platform/rate_limit/models.py`
for policy and scheduling math, `redis_bucket.py` for the atomic Lua operation,
`local_bucket.py` for the bounded degraded path, `identity.py` for peer/proxy
normalization, and `src/event_platform/api/middleware/rate_limit.py` for HTTP
classification and headers. Health and metrics are exempt by default.
