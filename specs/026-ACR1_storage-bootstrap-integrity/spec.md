# Feature Specification: ACR1 Storage Bootstrap Integrity

**Feature**: 026-ACR1_storage-bootstrap-integrity
**Status**: Draft
**Source findings**: ACR1-A P1-001, P2-004; ACR1-B P0-01, P1-14, P2-02, P2-04, P2-13

## User Scenarios & Testing

### User Story 1 - Start safely on empty storage (Priority: P1)

An operator starts the service against an empty canonical database and knows required uniqueness, query, checkpoint, lease, and rebuild structures exist before traffic is accepted.

**Independent Test**: Start against empty storage without test-side bootstrap, ingest duplicate event identities, and verify readiness and uniqueness behavior.

**Acceptance Scenarios**:

1. **Given** empty compatible storage, **When** startup completes, **Then** every required named structure exists before readiness succeeds.
2. **Given** bootstrap cannot establish a required invariant, **When** startup runs, **Then** the service fails readiness with a classified, bounded diagnostic and accepts no ingestion.

### User Story 2 - Govern schema changes explicitly (Priority: P2)

A release operator applies versioned storage/search bootstrap separately from replicated application startup and can verify compatibility without replicas racing to mutate shared schema.

### Edge Cases

- A required index exists with an incompatible definition or duplicate data blocks uniqueness creation.
- Production configuration omits canonical storage while derived dependencies are present.
- Workload evidence does not justify a proposed compound index.

## Functional Requirements

- **FR-001**: Startup MUST verify the canonical event identity uniqueness invariant before accepting requests.
- **FR-002**: Canonical query, projection checkpoint, rebuild record, and rebuild lease access paths MUST have explicit named storage definitions.
- **FR-003**: Production-mode configuration MUST reject missing canonical storage.
- **FR-004**: Bootstrap MUST be idempotent and safe when multiple release actors attempt it, while application replicas perform compatibility verification only.
- **FR-005**: Schema state MUST expose a version that startup can compare with the application compatibility range.
- **FR-006**: Compound indexes MUST be selected from measured query shapes and documented query-plan evidence rather than every possible filter permutation.
- **FR-007**: Bootstrap failures MUST use bounded structured logs and MUST NOT expose credentials or raw records.
- **FR-008**: Tests MUST prove empty-storage startup, incompatible-schema failure, uniqueness enforcement, and operational lookup behavior.

## Key Entities

- **Schema Version**: The applied canonical and operational storage contract.
- **Bootstrap Definition**: A named, idempotent required structure and its expected shape.
- **Compatibility Result**: Startup decision with safe mismatch diagnostics.

## Success Criteria

- **SC-001**: An empty environment becomes ready with all required structures and no test-only bootstrap.
- **SC-002**: Duplicate canonical event identities are rejected in every supported runtime path.
- **SC-003**: Missing or incompatible production storage prevents readiness in 100% of covered cases.
- **SC-004**: Query-plan evidence accompanies every newly added compound index.

## Assumptions and Scope

- Canonical storage remains authoritative; search and cache stores remain derived.
- This feature establishes migration ownership and compatibility checks; it does not introduce automatic destructive migrations.
