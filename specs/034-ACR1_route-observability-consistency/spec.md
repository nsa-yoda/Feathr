# Feature Specification: ACR1 Route and Observability Consistency

**Feature**: `034-ACR1_route-observability-consistency`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P2-002; AUTO_CODE_REVIEW_1_B P1-10, P2-05, P2-06, P3-05

## User Scenarios & Testing

### User Story 1 - Apply policy to the route that actually ran (Priority: P1)

As an operator, I can trust that rate limits, metrics, and logs identify every endpoint and HTTP method with the same canonical operation name.

**Independent Test**: Enumerate the live router and prove each method/path pair maps exactly once to a policy and observability definition.

**Acceptance Scenarios**:

1. **Given** any registered endpoint, **When** it handles a request, **Then** route policy and metrics use its canonical operation identity.
2. **Given** a new route without policy metadata, **When** validation runs, **Then** CI fails rather than silently assigning the wrong class.
3. **Given** 404, 405, and validation failures, **When** they are emitted, **Then** they use bounded fallback classifications and the shared problem contract.

### User Story 2 - Diagnose service and dependency behavior (Priority: P1)

As an operator, I can identify latency, saturation, backlog age, projection lag, and health-probe delays without high-cardinality telemetry.

**Acceptance Scenarios**:

1. **Given** queue or projection delay, **When** metrics are inspected, **Then** depth, oldest age, lag, batch size, and processing duration are available.
2. **Given** a slow dependency, **When** readiness is checked, **Then** probes run concurrently within a bounded deadline and report component latency.
3. **Given** a liveness request, **When** dependencies are unavailable, **Then** the cheap process-liveness check remains independent.

## Edge Cases

- The same path supports multiple methods with different policies.
- Framework-normalized route templates differ from raw request paths.
- A request fails before route resolution.
- One readiness probe hangs while others complete.
- Telemetry exporters are unavailable during shutdown.

## Functional Requirements

- **FR-001**: One typed route-operation registry MUST be derived from or validated against the live application router.
- **FR-002**: Rate-limit class, operation name, metrics labels, and API documentation MUST reference that registry.
- **FR-003**: CI MUST fail for unclassified routes, duplicate operation identities, or policy entries that match no live route.
- **FR-004**: Method-specific policies MUST be supported without raw-path cardinality.
- **FR-005**: Metrics MUST cover request latency, active requests, queue depth and age, worker duration, projection lag, batch size, rebuild duration, cache state, and limiter outcomes.
- **FR-006**: Metric labels MUST remain bounded and MUST exclude raw identifiers, URLs, request bodies, and credentials.
- **FR-007**: Readiness dependency probes MUST run concurrently with per-probe and overall deadlines.
- **FR-008**: Health output MUST report bounded component status and probe latency without exposing secrets.
- **FR-009**: Liveness MUST remain a cheap process check that does not require external dependencies.
- **FR-010**: Logs, metrics, and traces MUST share request and operation correlation identifiers where tracing is configured.

## Key Entities

- **Route Operation**: Canonical method, path template, operation name, policy class, and documentation identity.
- **Probe Result**: Component status, latency, reason class, and observation time.
- **Telemetry Contract**: Bounded metric and correlation fields for an operation.

## Success Criteria

- **SC-001**: Router enumeration finds zero unclassified or stale policy entries.
- **SC-002**: Every request outcome, including routing failures, has a bounded route classification.
- **SC-003**: Readiness completes within its overall deadline even when one dependency probe hangs.
- **SC-004**: Cardinality tests show no raw paths, event IDs, client IDs, or URLs in metric labels.

## Assumptions and Scope

- Authentication of operational endpoints is owned by the production security feature.
- This spec extends current structured logging and metrics rather than replacing their external formats without migration.
