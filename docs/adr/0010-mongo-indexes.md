# ADR 0010: Use query-shaped Mongo indexes, not metadata/index combinatorics

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Index event ID uniquely and add a small set of compound indexes for timestamp, type+time, user+time, and source URL+time. Do not index arbitrary metadata or every filter permutation.

## Rationale

Indexes accelerate known access paths but impose write amplification and working-set cost. Elasticsearch owns metadata search.

## Consequences

Some multi-filter queries may use a selective prefix index plus residual filtering. Explain plans with tests/docs rather than hiding tradeoffs.
