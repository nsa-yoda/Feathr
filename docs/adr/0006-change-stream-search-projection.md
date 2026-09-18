# ADR 0006: Project Mongo events into Elasticsearch through Change Streams

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Use MongoDB Change Streams for normal live search projection and persist resume tokens only after successful ES indexing.

## Rationale

This decouples search availability from event durability while giving a resumable, low-latency feed directly from canonical state. A local single-node replica set enables the same mechanism in Docker Compose.

## Consequences

Search is eventually consistent. Invalid/expired resume history must fail visibly and lead to reconciliation/rebuild instead of silent gaps.
