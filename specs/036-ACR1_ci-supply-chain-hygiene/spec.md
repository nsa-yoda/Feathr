# Feature Specification: ACR1 CI, Supply Chain, and Repository Hygiene

**Feature**: `036-ACR1_ci-supply-chain-hygiene`
**Status**: Draft
**Source findings**: AUTO_CODE_REVIEW_1 A P2-007; AUTO_CODE_REVIEW_1_B P2-07, P2-14 and Redundancy Removal Log

## User Scenarios & Testing

### User Story 1 - Trust the integration gate (Priority: P1)

As a reviewer, I can trust that a green CI run exercised required dependency-backed integration behavior rather than silently skipping it.

**Independent Test**: Run CI in a clean environment and inspect machine-readable results for every required suite and dependency.

**Acceptance Scenarios**:

1. **Given** required integration services are healthy, **When** CI runs, **Then** all required integration tests execute and report results.
2. **Given** a required service cannot start, **When** CI runs, **Then** the gate fails with a classified infrastructure reason rather than passing through skips.
3. **Given** coverage enforcement, **When** the measured value falls below the declared threshold, **Then** CI fails using the documented command.

### User Story 2 - Build auditable artifacts (Priority: P1)

As an operator, I can trace a release to immutable build inputs and inspect its dependency and vulnerability evidence.

**Acceptance Scenarios**:

1. **Given** a release build, **When** artifacts are produced, **Then** base images, CI actions, and build tools resolve to immutable versions.
2. **Given** a built image, **When** release evidence is inspected, **Then** an SBOM, vulnerability scan result, and provenance record are available.

### User Story 3 - Work from a clean repository and archive (Priority: P2)

As a maintainer, I do not encounter stale scripts, cache output, AppleDouble files, or placeholder packages that imply unsupported behavior.

**Acceptance Scenarios**:

1. **Given** a source archive, **When** it is inspected, **Then** generated caches and platform metadata are absent.
2. **Given** a script or empty package, **When** no supported workflow references it, **Then** it is removed or documented with an owner and purpose.

## Edge Cases

- A test is optional on developer machines but required in CI.
- A vulnerability database is temporarily unavailable.
- An immutable action digest has a newer human-readable release tag.
- A placeholder directory is required by packaging despite containing no source.
- Source archive exclusions accidentally omit a required fixture.

## Functional Requirements

- **FR-001**: CI MUST provision and health-check every dependency required by mandatory integration and failure tests.
- **FR-002**: Mandatory CI suites MUST fail on missing prerequisites and MUST NOT silently pass through skips.
- **FR-003**: Local optional skips MUST be distinguishable from CI-required execution in reports.
- **FR-004**: The documented coverage command and threshold MUST be enforced by CI.
- **FR-005**: Container base images and release dependencies MUST use immutable digests or equivalent locked identities.
- **FR-006**: Third-party CI actions and tool installers MUST be pinned and updated through a reviewable process.
- **FR-007**: Release builds MUST produce an SBOM, vulnerability result, and artifact provenance tied to the revision.
- **FR-008**: Dependency and image scanning policy MUST define severity disposition and an auditable exception path.
- **FR-009**: Source archives and committed files MUST exclude interpreter caches, test caches, editor debris, and platform metadata.
- **FR-010**: Stale scripts, compatibility shims, and empty packages MUST be removed unless a verified consumer and owner are documented.
- **FR-011**: Archive validation MUST prove required source, specs, fixtures, and lockfiles remain present.

## Key Entities

- **CI Gate Result**: Suite identity, execution state, prerequisites, and classified failure reason.
- **Build Provenance**: Revision, immutable inputs, artifact identity, and build environment evidence.
- **Repository Hygiene Rule**: Included and excluded file classes plus verified exceptions.

## Success Criteria

- **SC-001**: A green clean-room CI run reports zero skipped mandatory integration or failure tests.
- **SC-002**: Every release artifact has revision-linked SBOM, scan, and provenance evidence.
- **SC-003**: Automated archive inspection finds no cache directories, bytecode, or platform metadata.
- **SC-004**: Every retained compatibility script or placeholder directory has a verified consumer and owner.

## Assumptions and Scope

- Vulnerability policy may allow time-bounded reviewed exceptions; it may not silently suppress findings.
- Historical specs and accepted architecture records are retained as project evidence, not treated as debris.
