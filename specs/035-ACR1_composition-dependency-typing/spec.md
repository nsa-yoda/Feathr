# Feature Specification: ACR1 Composition and Dependency Typing

**Feature**: `035-ACR1_composition-dependency-typing`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P3-001, P3-002; AUTO_CODE_REVIEW_1_B P2-15, P3-04

## User Scenarios & Testing

### User Story 1 - Change one subsystem without editing a god module (Priority: P2)

As a maintainer, I can construct API, worker, projection, rebuild, and observability components through small typed composition modules with visible lifecycle ownership.

**Independent Test**: Replace one adapter with a test double through its typed factory and start the application without unrelated wiring changes.

**Acceptance Scenarios**:

1. **Given** application startup, **When** components are assembled, **Then** construction and lifespan ordering are visible without a single monolithic composition function.
2. **Given** a required service is unavailable, **When** a route resolves its dependency, **Then** it returns a deliberate typed service-unavailable problem.
3. **Given** a programmer wiring error, **When** validation runs, **Then** it fails during startup or static checking rather than through untyped request-state lookup.

### User Story 2 - Reuse boundary behavior consistently (Priority: P2)

As an API maintainer, I use shared request-context and problem helpers so request IDs and error contracts do not drift across routes.

**Acceptance Scenarios**:

1. **Given** any route error, **When** the problem response is built, **Then** it uses the shared typed contract and request context.
2. **Given** test application construction, **When** only a required subsystem is supplied, **Then** optional dependencies have explicit defaults or states.

## Edge Cases

- Startup fails halfway through component construction.
- Two components claim ownership of the same client.
- A degraded optional dependency is absent.
- A test constructs only a route subset.
- Shutdown occurs while startup is still unwinding.

## Functional Requirements

- **FR-001**: Composition MUST be split into cohesive factories for infrastructure, domain services, workers, API routes, and observability.
- **FR-002**: One typed application-services container or equivalent boundary MUST replace ad hoc untyped request-state lookups.
- **FR-003**: Required and optional dependencies MUST be explicit in types and startup validation.
- **FR-004**: Network-client creation, ownership, and close order MUST remain visible in lifespan composition.
- **FR-005**: Partial startup failure MUST unwind already-created resources exactly once.
- **FR-006**: Missing or degraded dependencies MUST map to deliberate typed outcomes rather than broad exception handling.
- **FR-007**: Request ID extraction and problem-response construction MUST use shared helpers.
- **FR-008**: OpenAPI problem declarations MUST be reusable and consistent with runtime handlers.
- **FR-009**: Factories MUST support focused tests without introducing a general-purpose dependency injection framework.
- **FR-010**: Architectural tests MUST prevent route modules from directly constructing infrastructure clients.

## Key Entities

- **Application Services**: Typed references to services made available to API and background components.
- **Component Factory**: Cohesive construction boundary with declared inputs and ownership.
- **Request Context**: Request ID, operation identity, and safe caller context shared by handlers.

## Success Criteria

- **SC-001**: Static checks find no untyped dependency lookup in route handlers.
- **SC-002**: Failure-injection tests prove partial startup closes every created client exactly once.
- **SC-003**: API contract tests show runtime and OpenAPI problem responses agree.
- **SC-004**: A subsystem test double can be installed without editing unrelated composition modules.

## Assumptions and Scope

- The goal is explicit modular composition, not adoption of a dependency injection framework.
- Service boundaries continue to follow the accepted architecture and ADRs.
