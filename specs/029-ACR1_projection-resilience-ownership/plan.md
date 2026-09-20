# Implementation Plan: ACR1 Projection Resilience and Ownership

## Summary

Keep projection degradable and checkpoint progress fenced to one logical owner. Add bounded owner/generation metadata, stale-generation rejection at the Mongo checkpoint boundary, and a bounded batch entry point while preserving the existing checkpoint-after-write ordering.

## Design

- `ProjectionCheckpoint` carries bounded owner and monotonic generation metadata.
- `SearchProjector` accepts explicit ownership and exposes `project_batch` with a hard bound.
- Mongo checkpoint replacement permits only the current or newer generation and reports owner loss safely.
- Existing retry, degraded health, and canonical persistence separation remain unchanged.
