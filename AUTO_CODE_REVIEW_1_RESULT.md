# ACR1 Implementation Results

All 12 `specs/*-ACR1_*` specifications were implemented, converged, reviewed, and committed. Each feature has an implementation commit and a separate post-commit work-log evidence commit.

| Spec | Problem | Solution | Evidence |
|---|---|---|---|
| [026-ACR1_storage-bootstrap-integrity](specs/026-ACR1_storage-bootstrap-integrity/spec.md) | Mongo schema and index ownership, compatibility, and startup safety were implicit. | Added a versioned storage manifest, idempotent bootstrap and verify CLI commands, startup verification, production Mongo enforcement, Compose ordering, and safe structured diagnostics. | `70f2f17`; work-log `63c7be3`; implementation-time unit suite passed 335 tests. |
| [027-ACR1_lifecycle-delivery-safety](specs/027-ACR1_lifecycle-delivery-safety/spec.md) | Slow workers lacked visibility renewal, and cancellation-resistant tasks could outlive closed clients. | Added visibility heartbeats, stale-receipt classification, resource isolation during unsafe shutdown, drain telemetry, and bounded task policies. | `3892024`; work-log `1aa11ab`; focused suite passed 25 tests. |
| [028-ACR1_rebuild-convergence-operations](specs/028-ACR1_rebuild-convergence-operations/spec.md) | Rebuild fencing, historical lookup, and post-swap cleanup safety were incomplete. | Added fencing metadata, monotonic lease fencing, rebuild lookup by ID, runtime state wiring, and an alias-swap cleanup barrier. | `9e8b74f`; work-log `fef3c1f`; focused rebuild/lifecycle suite passed 16 tests. |
| [029-ACR1_projection-resilience-ownership](specs/029-ACR1_projection-resilience-ownership/spec.md) | Stale projectors could regress checkpoints, and batching boundaries were implicit. | Added checkpoint owner/generation fencing, stale-generation rejection, and bounded batch projection. | `22338cc`; work-log `0d9bc85`; projection suite passed 27 tests. |
| [030-ACR1_request-idempotency](specs/030-ACR1_request-idempotency/spec.md) | `Idempotency-Key` only contributed a hash; retries could not replay outcomes or coordinate replicas. | Added durable Mongo and in-memory registries, atomic reservation/replay/conflict handling, replay-window settings, and safe conflict responses. | `c638ee5`; work-log `6c7ea99`; ingestion/registry suite passed 8 tests. |
| [031-ACR1_cursor-api-boundary-hardening](specs/031-ACR1_cursor-api-boundary-hardening/spec.md) | Cursor keys were generated per process, and public DTOs exposed persistence fields. | Added shared current/previous signing-key configuration, rotation overlap, `PublicEvent` DTOs, and URL credential rejection. | `c0efa6b`; work-log `dad7e7a`; boundary suite passed 81 tests. |
| [032-ACR1_queue-performance-durability](specs/032-ACR1_queue-performance-durability/spec.md) | Queue receive and expiry paths scanned the full backlog; local durability semantics were implicit. | Replaced scans with a ready deque and expiry heap, preserved receipt safety, and exposed `durable=False` for the local adapter. | `1e2da3d`; work-log `4f4ad19`; queue/retry/lifecycle suite passed 47 tests. |
| [033-ACR1_analytics-cache-scalability](specs/033-ACR1_analytics-cache-scalability/spec.md) | Cancelling one cache waiter could cancel shared refresh work. | Shielded shared refresh tasks while retaining bounded aggregation, cache validation, TTL, and degraded fallback behavior. | `f9d2095`; work-log `65f23c5`; realtime suite passed 19 tests. |
| [034-ACR1_route-observability-consistency](specs/034-ACR1_route-observability-consistency/spec.md) | Readiness probes ran serially and could be delayed by one dependency. | Added concurrent per-probe and overall deadlines while preserving cheap liveness and bounded metric labels. | `f4abe83`; work-log `0ecea22`; health suite passed 6 tests. |
| [035-ACR1_composition-dependency-typing](specs/035-ACR1_composition-dependency-typing/spec.md) | Runtime dependencies were spread across untyped `app.state` lookups. | Added a typed `ApplicationServices` container and factory, wiring lifespan-owned dependencies without a general DI framework. | `8ec73bb`; work-log `2cee67c`; composition/lifecycle suite passed 7 tests. |
| [036-ACR1_ci-supply-chain-hygiene](specs/036-ACR1_ci-supply-chain-hygiene/spec.md) | Optional integration skips could appear green, and archive cleanliness was not enforced. | Added `make test-integration-required`, JUnit skip failure detection, `make check-source-archive`, and CI archive validation. | `c056f2d`; work-log `40b88a1`; archive and developer workflow checks passed. |
| [037-ACR1_production-security-boundary](specs/037-ACR1_production-security-boundary/spec.md) | Production lacked a fail-closed authentication boundary and placeholder-secret enforcement. | Added production bearer authentication, token validation, shared cursor/Mongo requirements, HSTS, and security regression coverage. | `c2d2712`; work-log `31fd583`; full unit suite passed 351 tests. |

## Final validation

- Full unit suite: **351 passed**
- Failure suite: **29 passed**
- Integration suite: **12 explicit skips** because `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL` were not configured
- Ruff format and lint: **passed**
- Strict mypy: **passed for 58 source files**
- Docker Compose configuration: **passed**
- Source archive validation: **passed**
- Focused Feature 026–037 suites: passed as recorded above

The required `make` targets were attempted, but the installed `uv` executable failed before project execution with the host-level macOS system-configuration panic `Attempted to create a NULL object`. Equivalent direct `.venv` gates passed. Live Mongo/Elasticsearch/Redis integration, Compose smoke, Postman, hosted CI, SBOM, and provenance evidence remain environment-dependent.

The append-only work log is [`CODEX_WORK.LOG`](CODEX_WORK.LOG). The final implementation commits are on `main`; unrelated pre-existing untracked review/input/archive files were left untouched.
