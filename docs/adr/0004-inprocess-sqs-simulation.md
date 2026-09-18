# ADR 0004: Model SQS semantics in-process with explicit limitations

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Implement a bounded in-process queue with message/receipt identity, visibility timeout, delete-on-success, redelivery, retry visibility changes, and DLQ redrive.

## Rationale

The assessment explicitly calls for an in-process SQS-style simulation. Modeling receive/delete semantics demonstrates queue reasoning better than a simple `asyncio.Queue` consumer that permanently removes on `get()`.

## Consequences

The demo runs one app process. Queue acceptance is not durable across crash. These limitations are documented rather than hidden.
