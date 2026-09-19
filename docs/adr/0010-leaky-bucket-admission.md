# ADR 0010: Queue bursts with bounded leaky-bucket admission

**Status:** Accepted
**Date:** 2026-09-19

## Decision

Rate limiting uses an atomic Redis leaky bucket per normalized identity and route class. An admitted request reserves a release slot and waits asynchronously until that slot. A request receives `429` only when the bounded reservation backlog is full. Redis failure uses the same scheduling model in a stricter bounded process-local fallback.

The ingestion default is a 1,000-request backlog leaking at 100 requests per second. This accommodates the reviewer UI's 500 requests over five seconds without a normal-path rejection and keeps the maximum configured backlog delay near ten seconds. Request cancellation may leave a reserved slot that drains naturally; it never creates a false `202` response.

## Rationale

Immediate token-bucket rejection discards valid bursts and makes client retries amplify load. Reserving release slots applies backpressure while preserving accepted HTTP requests. A hard bound is still required so abusive or failed traffic cannot consume unbounded memory, connections, or Redis state.

## Consequences

Queued requests consume an open HTTP request until release, so capacities and leak rates must remain below proxy and client timeouts. Overflow still returns a safe `429` with `Retry-After`. Redis remains non-authoritative and local fallback remains observable and bounded.
