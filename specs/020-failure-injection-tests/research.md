# Feature 020 Research Notes

## Existing evidence

- `PersistenceWorker` already acknowledges only after canonical insert or same-payload duplicate verification, and classifies Mongo failures for visibility retry or DLQ disposition.
- `InProcessQueue` already provides bounded capacity, injected clock/visibility semantics, source-preserving failed DLQ behavior, and safe DLQ entries.
- `HealthRegistry` provides injectable component probes and fail-closed readiness for Mongo, queue, and persistence worker.
- `SearchProjector` saves checkpoints after derived writes, retains the prior checkpoint on writer failure, and exposes `reconciliation_required` for invalid resume history.
- `RealtimeStatsService` and `RateLimiter` already expose Redis cache bypass and local fallback ports.
- `SearchRebuilder` verifies target counts before alias swap and records failed runs while cleaning the target.
- Existing unit tests cover individual pieces, while `tests/failure/` lacks a single Feature 020 acceptance selection tying each requested invariant to deterministic fault seams.

## Decisions

1. Add failure-injection tests under `tests/failure/` and reuse existing ports/fakes where possible. Production defaults remain unchanged.
2. Use manual clocks, immediate retry policies, explicit failing/recovering stores/writers, and in-memory alias state. No random failures, process-killing chaos, fixed long sleeps, or unavailable external services.
3. Keep canonical Mongo assertions independent from Elasticsearch and Redis assertions. ES outage must not be represented as a Mongo outage, and Redis outage must not alter canonical statistics.
4. Treat stale/invalid resume history as a reconciliation/rebuild requirement; never fall back to a latest-only stream.
5. Treat an alias as unchanged until verification and atomic swap succeed; failed targets are recorded and cleaned when the port supports deletion.
6. Classify unexpected rebuild dependency/cleanup exceptions as a bounded `rebuild_unexpected_failure`, persist failed state when possible, and keep target cleanup/live-target deactivation independent and safe.
7. Record exact test counts and service-availability limits in traceability, workflow, README/testing strategy, and the feature review report.
