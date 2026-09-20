# ADR 0010: Use query-shaped Mongo indexes, not metadata/index combinatorics

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Index event ID uniquely and add a small set of compound indexes for timestamp, type+time, user+time, and source URL+time. Do not index arbitrary metadata or every filter permutation.

## Rationale

Indexes accelerate known access paths but impose write amplification and working-set cost. Elasticsearch owns metadata search.

## Consequences

Some multi-filter queries may use a selective prefix index plus residual filtering. Explain plans with tests/docs rather than hiding tradeoffs.

The versioned storage manifest in `src/event_platform/storage/bootstrap.py` owns
the operational checkpoint and rebuild indexes alongside these event indexes.
`storage bootstrap` is the additive release-time mutation actor; application
startup verifies the live definitions and schema fingerprint without mutating
shared storage. New compound indexes require measured query-plan evidence and a
schema compatibility decision.
