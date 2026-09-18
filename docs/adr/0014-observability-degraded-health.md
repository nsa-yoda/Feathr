# ADR 0014: Expose explicit component degradation instead of binary service health

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Provide JSON logs, metrics, liveness, readiness, and component health. Mongo failure makes core readiness fail; ES/Redis can mark degraded while unaffected capabilities remain available.

## Rationale

A distributed-data service is rarely simply "up" or "down". Reviewers and operators need to know which capability is impaired.

## Consequences

Health endpoints have defined semantics and must not perform unbounded expensive checks.
