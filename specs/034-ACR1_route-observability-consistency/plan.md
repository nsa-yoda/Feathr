# Implementation Plan: ACR1 Route Observability Consistency

## Summary

Make dependency readiness probes concurrent and deadline-bounded while retaining cheap liveness and bounded metric labels. The existing middleware remains the single request/operation correlation source.

## Design

- `HealthRegistry` runs all configured probes concurrently with per-probe and overall deadlines.
- Timeout/failure produces bounded `probe_failed` component state and safe logs.
- Existing route normalization and metric vocabulary remain fixed-cardinality.
