# Implementation Plan: Graceful Lifecycle and Worker Supervision

**Branch**: `016-graceful-lifecycle` | **Status**: Accepted

## Technical approach

Create a small `LifecycleSupervisor` owning an async stop event, named managed
tasks, state snapshots, bounded drain, cancellation, safe failure reporting,
and deterministic resource close callbacks. Add queue admission shutdown
separate from full queue close. Integrate the supervisor into the FastAPI
lifespan while retaining optional dependency clients and existing worker/
projector boundaries. Health probes read supervisor state.

## Close order

1. Mark lifecycle draining and stop queue admission.
2. Signal managed worker/projector tasks.
3. Wait up to the configured grace period; cancel and gather leftovers.
4. Log queue depth and close the queue.
5. Close Redis, Elasticsearch, and Mongo clients in that order.

## Constitution check

PASS: all clients/tasks are lifespan-owned, async I/O remains non-blocking,
unexpected failures are classified and logged, and persistence acknowledgement
semantics are unchanged.
