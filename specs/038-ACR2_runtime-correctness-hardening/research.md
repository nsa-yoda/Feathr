# Research Notes: ACR2 Runtime Correctness and Production Readiness

## Verified baseline

- `LifecycleSupervisor.request_shutdown()` currently stops admission and sets the same stop event consumed by persistence workers, so queued accepted messages can remain when shutdown proceeds.
- `TaskPolicy.criticality` is present in the model, but task exit/error handling currently treats degradable and critical tasks alike.
- The events route reserves idempotency before queue admission and completes afterward, with no owner-fenced release or completion state.
- Mongo stale reservation takeover updates by identifier and fingerprint without a generation/owner compare-and-set.
- Request scope defaults to `anonymous` because middleware does not consistently set a client scope.
- Search projector checkpointing has owner/generation fields but no live lease/fencing owner acquisition in the API composition path.
- Rate-limit classification does not match `/events/search`, and delayed requests have no process-wide bounded admission gate.
- Queue explicit IDs overwrite the message map while still appending another ready entry.
- Storage manifests, CI gates, README, ARCHITECTURE, and coverage enforcement contain the P2/P3 drift described by the review.

## Decisions

- Keep the simulated in-process queue and document its crash-loss limitation; do not substitute an external broker.
- Use Mongo atomic operations for correctness that spans replicas.
- Treat Elasticsearch/Redis failure as derived-service degradation unless canonical persistence is affected.
- Use bounded batches and retries rather than unbounded task creation or one-document network calls.
- Defer a complete external identity provider, materialized analytics rollups, and a production rebuild CLI only when the final report records the assignment boundary and next design step.

## Validation strategy

Focused unit tests will cover each corrected transition first. Integration/failure tests will use real Mongo/Redis/Elasticsearch when available; unavailable services will be reported with the exact command and reason. Full quality gates will run after P0/P1 implementation and again after P2/P3 documentation and CI changes.
