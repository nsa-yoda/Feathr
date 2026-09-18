# ADR 0012: Run one application process while using an in-process queue

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

The Compose app service runs a single Uvicorn process. Background ingestion and projection workers live in that process.

## Rationale

Multiple application processes would each own a different queue, making load-balanced acceptance/worker semantics misleading. The assignment's queue constraint implies this limitation.

## Consequences

Horizontal API/worker scaling is deferred to the documented SQS migration. Concurrency within the process remains configurable and bounded.
