# ADR 0008: Use short-TTL cache-aside realtime statistics

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Cache realtime statistics in Redis with a configurable default TTL near 10 seconds. On miss, compute from Mongo and populate Redis. On Redis failure, compute and return without cache.

## Rationale

The endpoint is latency-oriented and tolerates modest staleness. TTL expiration avoids write-path invalidation on every event.

## Consequences

Responses expose cache outcome. Higher-scale evolution can use incremental/materialized counters.
