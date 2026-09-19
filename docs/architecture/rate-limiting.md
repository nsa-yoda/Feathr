# Rate Limiting Design Details

## Token bucket state

Per `(route_class, client_identity)` store current token balance and last refill timestamp. Redis execution must atomically refill, evaluate cost, decrement when allowed, set/refresh bounded expiry, and return enough information to compute retry/remaining headers.

## Route costs

Keep costs simple and documented. Search/analytics may have stricter capacities than cheap canonical reads. Do not create per-URL path-cardinality keys from arbitrary IDs; classify by route template.

## Local fallback

Use the same token-bucket semantics with intentionally stricter capacity/refill. Store entries in a bounded TTL/LRU-like structure so hostile unique IPs cannot leak memory indefinitely.

## Proxy identity

By default identity is socket peer address. Only when trusted proxy hops are configured should forwarded chain parsing choose the client address. Malformed chains fall back safely and are never trusted more broadly than configured.

## Response headers

Define and test consistent `Retry-After`; include `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset`. Never include raw Redis keys.

The implementation is split between `src/event_platform/rate_limit/models.py`
for policy and token math, `redis_bucket.py` for the atomic Lua operation,
`local_bucket.py` for the bounded degraded path, `identity.py` for peer/proxy
normalization, and `src/event_platform/api/middleware/rate_limit.py` for HTTP
classification and headers. Health and metrics are exempt by default.
