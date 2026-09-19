# Rate Limit Module Boundary

`models.py` owns route policies and deterministic token math. `redis_bucket.py`
performs one atomic Lua refill/check/decrement, while `local_bucket.py` keeps a
stricter bounded fallback with idle eviction. `identity.py` derives direct-peer
or explicitly trusted-proxy identities. HTTP route classification and response
headers remain in `src/event_platform/api/middleware/rate_limit.py`.
