# Feature Specification: ACR2 Runtime Correctness and Production Readiness

**Feature Branch**: `038-ACR2_runtime-correctness-hardening`

**Created**: 2026-09-20

**Status**: Draft

**Input**: Remediate the independently verified findings in `AUTO_CODE_REVIEW_2.md` in strict P0 through P3 order.

**Source**: `AUTO_CODE_REVIEW_2.md` (P0-01 through P3-05), with existing fixes verified before implementation.

## User Scenarios & Testing

### User Story 1 - Accepted events survive graceful shutdown (Priority: P0)

As an API caller, when `POST /events` returns `202 Accepted`, I need the accepted event to remain eligible for persistence during graceful shutdown, with an explicit bounded-drain outcome if the process cannot finish.

**Independent Test**: Admit an event, immediately request shutdown, and verify the worker drains and persists it before normal shutdown; verify forced timeout leaves an observable residual-queue report.

**Acceptance Scenarios**:

1. **Given** an accepted queue message, **When** shutdown begins, **Then** new admission stops while the persistence worker continues until the queue is empty or the grace deadline expires.
2. **Given** the grace deadline expires, **When** shutdown completes, **Then** the process reports residual work and does not claim a clean drain.
3. **Given** a queue acknowledgement failure after Mongo persistence, **When** the message is redelivered, **Then** idempotent persistence prevents a duplicate canonical event.

### User Story 2 - Degradable projections do not stop ingestion (Priority: P0)

As an operator, I need a failed Elasticsearch projector to be reported as degraded while Mongo-backed ingestion and readiness continue operating.

**Independent Test**: Fail the projector after startup and verify the lifecycle supervisor records degradation, keeps the persistence worker and API available, and exposes a degraded search status.

**Acceptance Scenarios**:

1. **Given** a task marked `degradable`, **When** it exits or raises, **Then** the supervisor records the component failure without closing admission or marking canonical readiness failed.
2. **Given** a critical task failure, **When** it exits or raises, **Then** the supervisor performs the existing global failure transition.

### User Story 3 - Duplicate producers and projectors are safe (Priority: P1)

As a producer or horizontally scaled operator, I need concurrent duplicate submissions and projector replicas to have deterministic ownership and monotonic state transitions.

**Independent Test**: Run same-key producer requests concurrently, exercise stale reservation takeover and queue admission failure, then run two projector owners and verify only the lease holder can renew or checkpoint.

**Acceptance Scenarios**:

1. **Given** two same-key submissions, **When** they race, **Then** exactly one reservation owns queue admission and the other receives replay or in-flight semantics.
2. **Given** a stale reservation, **When** two owners attempt takeover, **Then** one CAS winner proceeds and the loser observes the winner's state.
3. **Given** a projector lease is lost, **When** the stale owner checkpoints, **Then** the checkpoint is rejected by fencing and the new owner can continue monotonically.

### User Story 4 - Operational guarantees are documented and enforced (Priority: P2)

As an operator and reviewer, I need CI, documentation, storage manifests, route policy, and repository hygiene to describe and enforce the runtime guarantees that the code actually provides.

**Independent Test**: Run the required quality gates, inspect the generated architecture and README claims, and verify storage/bootstrap/rate-limit/coverage regression tests.

## Edge Cases

- Shutdown starts while a message is invisible, while Mongo persistence is active, or after persistence but before acknowledgement.
- A queue send fails after reservation, a completion write fails after queue admission, or the process crashes in either window.
- A degradable task exits normally, raises, or is cancelled while a critical task is still healthy.
- Multiple API replicas race on a fresh or expired idempotency record.
- A projector loses its lease during a bulk write and a stale checkpoint attempt arrives after takeover.
- Redis is unavailable, delayed rate-limit capacity is exhausted, or a caller disconnects while waiting.
- An explicit duplicate queue message ID is submitted while the original is ready or invisible.
- A route classification change affects search, analytics, rebuild, health, or metrics semantics.

## Requirements

### Functional Requirements

- **FR-001**: Shutdown MUST stop new queue admission before draining and MUST keep canonical persistence work runnable until the queue is empty or a documented grace deadline expires.
- **FR-002**: Shutdown MUST report residual queue work and task outcomes; it MUST NOT report a clean drain after forced cancellation.
- **FR-003**: Task criticality MUST control lifecycle behavior: critical failures stop canonical service; degradable failures record degradation without stopping canonical ingestion.
- **FR-004**: Canonical readiness MUST depend on Mongo and persistence worker health, not Elasticsearch or Redis derived-service health.
- **FR-005**: Producer idempotency MUST use atomic compare-and-set state transitions with an owner token, lease/generation, scope, and explicit queue-admission failure recovery.
- **FR-006**: Idempotency completion and release MUST be owner-fenced; stale owners MUST NOT overwrite a newer reservation.
- **FR-007**: The idempotency scope MUST use a stable authenticated client or tenant identity when available and MUST document the single-client local fallback.
- **FR-008**: Elasticsearch projection MUST use an explicit lease/fencing model, monotonic checkpoint ownership, bounded bulk writes, and retry handling for partial failures.
- **FR-009**: Rate-limit classification MUST match actual API routes, and delayed admission MUST have a bounded process-wide backlog that is the final condition for `429`.
- **FR-010**: Queue message IDs MUST not create duplicate ready entries; active duplicate IDs MUST have explicit idempotent behavior.
- **FR-011**: The idempotency collection and projection lease/checkpoint collections MUST be represented in the storage manifest and bootstrap/index policy.
- **FR-012**: CI MUST fail when required integration/failure/coverage gates fail or are skipped without an explicit infrastructure reason.
- **FR-013**: README, ARCHITECTURE, operational docs, configuration examples, and comments MUST describe actual shutdown, projection, cache, rate-limit, and deployment guarantees.
- **FR-014**: The implementation MUST preserve FastAPI, MongoDB/PyMongo Async, Elasticsearch, Redis, and the simulated in-process queue required by the assignment.
- **FR-015**: Review findings that are production-evolution concerns rather than assignment defects (multi-tenant identity provider, high-volume analytics rollups, and a fully wired rebuild CLI) MUST be explicitly documented with evidence and a defensible follow-up path if not implemented.

### Key Entities

- **Idempotency Record**: Scoped producer key, request fingerprint, event ID, owner token, generation, status, lease timestamps, and completion metadata.
- **Queue Message**: Stable message ID, visibility receipt, retry count, and acknowledgement state.
- **Lifecycle Task**: Named factory, criticality, shutdown mode, restart policy, health/degradation state, and failure evidence.
- **Projection Lease**: Projector name, owner ID, fencing generation, expiry, and renewal state.
- **Projection Checkpoint**: Source position, owner, fencing generation, and monotonic commit metadata.
- **Storage Manifest Entry**: Canonical/derived collection, required indexes, retention policy, and bootstrap invariant.

## Success Criteria

- **SC-001**: Focused lifecycle tests prove accepted events are persisted during normal drain and residual work is reported on timeout.
- **SC-002**: Focused task-policy tests prove degradable projector failure leaves canonical readiness and ingestion available.
- **SC-003**: Concurrency tests prove one winner for same-key reservation, stale takeover, queue-failure recovery, and lease-fenced checkpoints.
- **SC-004**: Search projection tests prove bounded bulk writes, acknowledged-prefix checkpoints, and partial failure retry behavior.
- **SC-005**: Route-contract tests prove `/events/search`, analytics, rebuild, health, and metrics map to intended rate-limit classes.
- **SC-006**: Required local validation commands pass, with unavailable infrastructure and intentional deferrals recorded precisely.

## Assumptions

- The assignment's in-process queue remains intentionally volatile across process crashes; the production migration path is documented rather than silently replacing it.
- MongoDB is the canonical source of truth; Elasticsearch and Redis remain derived/degradable services.
- A configured static bearer token is the current assignment authentication boundary; stable token-derived scope is sufficient for this repository, while a real identity provider remains a documented production evolution.
- Tests may use fakes for deterministic unit behavior and real services for integration behavior when the local environment provides them.
- Changes are delivered in strict P0/P1/P2/P3 order with append-only evidence in `CODEX_WORK.LOG`.
