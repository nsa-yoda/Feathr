# Feature Specification: Developer Experience and CI

**Feature**: 024-developer-experience-ci  
**Status**: Accepted for implementation  
**Source**: [REQUEST.md](REQUEST.md)

## User Scenarios & Testing

### User Story 1 - Run standard checks locally (Priority: P1)

A developer uses documented Make targets to format, lint, type-check, run unit/integration/failure tests, run all tests, validate Compose, start/stop/reset the stack, smoke it, run Postman, and inspect or run a search rebuild.

**Acceptance Scenarios**

1. Every documented target has a deterministic command and fails with a useful exit code.
2. Compose lifecycle targets use the checked-in `.env.example` defaults and do not delete data unless reset is explicitly requested.

### User Story 2 - Receive reproducible CI feedback (Priority: P1)

A pull request runs formatting, lint, type-check, unit, failure, and integration checks using the lockfile and publishes concise diagnostics.

**Acceptance Scenarios**

1. CI uses the supported Python/uv versions and locked dependency resolution.
2. Unit and static failures are visible as separate steps; integration is allowed to skip only when service endpoints are unavailable.

## Functional Requirements

- **FR-001**: The project MUST provide Make targets for format, lint, typecheck, unit, integration, failure, all, Compose config/up/down/reset, smoke, Postman, coverage, and rebuild status/demo.
- **FR-002**: Default targets MUST use locked dependency resolution and preserve reproducible exit status.
- **FR-003**: CI MUST run format, lint, typecheck, unit, failure, integration, and Compose config checks on supported Python.
- **FR-004**: CI MUST cache dependencies without changing lockfile resolution and MUST upload diagnostic test/coverage artifacts when available.
- **FR-005**: README MUST document the target groups, supported runtime versions, Compose lifecycle, and rebuild CLI example.
- **FR-006**: Docker-free tests MUST validate Make target names, lock flags, CI steps, cache configuration, and documented command paths.

## Success Criteria

- **SC-001**: A new developer can discover and run the complete local quality gate from one README section.
- **SC-002**: CI exposes independent status for all required static/test stages on each pull request.
- **SC-003**: Re-running the same revision with the same lockfile produces the same dependency set.
- **SC-004**: Compose config validation and failure diagnostics are available without starting external services.

## Assumptions and Scope

- CI uses GitHub Actions and Ubuntu runners.
- Live Docker startup, browser, and Postman checks remain explicit runtime jobs/conditions rather than hidden local dependencies.
- The existing `uv.lock` is authoritative and is not regenerated for this feature.
