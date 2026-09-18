# ADR 0007: Use versioned Elasticsearch indices behind a stable alias for online rebuilds

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Searches and normal writes target `events-search`; physical generations use versioned names. Rebuilds create a new generation, dual-write live changes, bulk copy Mongo, verify, then atomically swap the alias.

## Rationale

In-place destructive rebuilds create downtime and make rollback difficult. Alias switching gives a clear verification boundary and safe rollback window.

## Consequences

Rebuild state, locking, progress, failures, alias transitions, and cleanup become explicit operational responsibilities.
