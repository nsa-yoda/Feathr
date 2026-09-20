# Implementation Plan: ACR1 Analytics Cache Scalability

## Summary

Harden analytics cache coalescing so one cancelled waiter cannot cancel shared computation, while retaining bounded canonical aggregation, cache schema validation, TTL, and explicit bypass behavior.

## Design

- Shield shared in-process refresh tasks from individual waiter cancellation.
- Keep raw-event aggregation bounded by window, event-type cardinality, and Mongo max-time deadline.
- Preserve Redis cache-aside and safe degraded bypass semantics; rollup rebuild remains a separate operational feature.
