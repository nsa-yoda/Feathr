# Implementation Plan: ACR1 Request Idempotency

## Summary

Add an explicit idempotency registry around event admission. The registry reserves a caller/operation/key identity against a canonical request fingerprint, replays completed outcomes, reports in-flight contention and stable conflicts, and uses a Mongo-backed record for configured deployments with an in-memory adapter for isolated local tests.

## Design

- Hash the registry identity and never expose raw keys or fingerprints.
- Reserve before queue admission and complete after successful enqueue.
- Use an atomic Mongo `_id` identity to converge concurrent replicas; retain a bounded replay window.
- Preserve the existing event payload hash for worker-level duplicate delivery safety.
