# Intended Module Boundary

Redis cache adapter and cache-aside concerns.

`realtime.py` owns the versioned deterministic realtime statistics payload,
short-TTL Redis adapter, cache failure classification, and bounded single-flight
coalescing. Redis is disposable; callers use canonical Mongo results on bypass.
