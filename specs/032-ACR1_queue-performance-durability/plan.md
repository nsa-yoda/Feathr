# Implementation Plan: ACR1 Queue Performance and Durability

## Summary

Replace ordinary local queue backlog scans with ready deque and expiry heap scheduling, preserve receipt-generation safety, and expose the local adapter's volatile capability explicitly so production topology cannot mistake `202` for crash-durable acceptance.

## Design

- Ready messages are dequeued directly; visibility expiries are promoted from a min-heap.
- Receipt handles remain validated against the current message generation.
- `InProcessQueue.durable` is explicit `False`; durable production adapters remain a deployment boundary.
