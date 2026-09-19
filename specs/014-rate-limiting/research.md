# Feature 014 Research

## Decisions

1. **Redis atomicity**: use one Lua script executed through Redis `EVAL` so refill, allowance, decrement, expiry, and returned metadata are one operation across service processes.
2. **Fallback**: use a monotonic-clock local token bucket with an ordered bounded map. Evict expired entries first, then the least recently used idle entry when the cap is reached.
3. **Identity**: direct peer host is canonical unless `trusted_proxy_hops > 0`; select the address immediately before the trusted proxy suffix and reject malformed chains.
4. **Headers**: use `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`, and integer `Retry-After` on denials and successful limited responses.
5. **Route wiring**: HTTP middleware classifies route templates before handlers; health and metrics are exempt by default.

## Rejected Alternatives

- Fixed-window counters: boundary bursts and non-atomic multi-step updates violate the requested token-bucket semantics.
- Fail-open on Redis errors: would remove abuse protection during a dependency outage.
- Unbounded local dictionaries: allow attacker-controlled identity cardinality to consume process memory.
- Blind trust of `X-Forwarded-For`: allows direct clients to select arbitrary buckets.
