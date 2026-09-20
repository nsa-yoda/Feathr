# Implementation Plan: ACR1 Lifecycle and Delivery Safety

**Branch**: `027-ACR1_lifecycle-delivery-safety` | **Spec**: [spec.md](spec.md)

## Summary

Harden the existing in-process lifecycle and persistence worker at the delivery boundary. Shutdown stops admission before bounded drain, records incomplete work, and leaves shared resources open when cancellation-resistant tasks remain attached. Long persistence renews visibility, stale receipt operations become ownership-loss outcomes, and task registration records bounded policy metadata.

## Design

1. `LifecycleSupervisor` measures drain duration, reports incomplete queue depth, and isolates resources if task cancellation does not terminate safely.
2. `TaskPolicy` makes criticality and bounded restart metadata explicit without introducing a DI framework.
3. `InProcessQueue` exposes its configured visibility interval; `PersistenceWorker` renews delivery visibility and classifies stale receipts safely.
4. Production settings reject zero visibility timeout; search projection is registered as degradable while canonical persistence remains critical.

## Validation

Focused lifecycle, worker, and settings tests cover shutdown ordering, cancellation-resistant tasks, visibility renewal, ownership loss, and production configuration.
