# ADR 0003: MongoDB is canonical; Elasticsearch and Redis are derived

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

MongoDB owns authoritative event state. Elasticsearch is a search projection. Redis holds short-lived cache and rate-limit state only.

## Rationale

This separates durability from optimization/search concerns and gives clear partial-failure behavior. It avoids pretending to have cross-store transactions.

## Consequences

ES and Redis outages degrade capabilities but cannot erase accepted Mongo-persisted events. Recovery mechanisms and stale-data semantics must be explicit.
