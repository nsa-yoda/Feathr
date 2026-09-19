# Feature Specification: Graceful Lifecycle and Worker Supervision

**Feature Branch**: `016-graceful-lifecycle`
**Status**: Accepted
**Input**: `REQUEST.md`

## User scenarios

### Deterministic startup

The service starts only after its configured dependency clients and local
processing resources have been created. Startup failures are classified and
reported as structured lifecycle events. A missing optional derived dependency
leaves the service explicitly degraded rather than creating an unowned client.

### Bounded shutdown

When the application lifespan ends, it stops accepting new queue messages,
signals workers and the projector to stop receiving, waits for in-flight work
for a configured grace period, cancels tasks that exceed the deadline, records
remaining queue depth, and closes clients in a deterministic order. A message is
acknowledged only after its existing persistence boundary succeeds.

### Supervision

Unexpected task termination transitions lifecycle and health state to failed,
emits a safe terminal exception type, and prevents readiness from claiming the
service is healthy. Normal stop and cancellation are not reported as failures.

## Requirements

- **FR-001**: Lifecycle MUST expose `starting`, `running`, `draining`, `stopped`, and `failed` states with bounded safe details.
- **FR-002**: Startup MUST own every created client/task and close or cancel it during failed startup and normal shutdown.
- **FR-003**: Shutdown MUST stop queue admission before signalling consumers and MUST wait no longer than the configured grace period before cancellation.
- **FR-004**: In-flight persistence work MUST retain the existing ack-after-persist boundary; unfinished work MUST remain unacknowledged.
- **FR-005**: Shutdown MUST record remaining queue depth because visible in-memory messages can be discarded with the process.
- **FR-006**: A supervised task that exits unexpectedly MUST mark lifecycle failed, emit a structured event with only the exception type, and make readiness false.
- **FR-007**: Client close ordering MUST be deterministic: worker/projector tasks, queue, Redis, Elasticsearch, then Mongo.
- **FR-008**: Tests MUST cover startup failure cleanup, bounded drain/cancellation, close order, queue admission stop, supervision failure, and health impact.

## Acceptance scenarios

1. A shutdown request prevents new queue sends while existing work receives a bounded drain window.
2. A task that raises transitions health to failed and produces a safe supervision log.
3. A slow task is cancelled after the grace period and all owned clients close in order.
4. A visible queue depth is logged before queue close; no unfinished delivery is acknowledged.

## Assumptions

- Mongo, Elasticsearch, and Redis URLs remain optional in local tests; configured
  clients are lifecycle-owned and unavailable optional services are degraded.
- The current in-process queue cannot durably preserve messages across process
  exit; shutdown reports its remaining depth for operators.
