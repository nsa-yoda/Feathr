# Implementation Plan: ACR1 Storage Bootstrap Integrity

**Branch**: `026-ACR1_storage-bootstrap-integrity` | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/026-ACR1_storage-bootstrap-integrity/spec.md`

## Summary

Add a versioned Mongo storage manifest covering canonical events, projection checkpoints, rebuild records, and rebuild leases. A separate idempotent CLI bootstrap actor creates the declared indexes and schema marker; application replicas only verify compatibility before starting workers or accepting traffic. Production configuration requires Mongo, Compose runs bootstrap after replica-set initialization and before the API, and integration evidence proves empty-storage startup and incompatible-schema failure.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI, Pydantic v2, PyMongo Async API 4.x

**Storage**: MongoDB 7 replica set; Mongo remains canonical

**Testing**: pytest unit tests plus real-Mongo integration tests selected with `MONGO_URI`

**Target Platform**: Linux container and local Python runtime

**Project Type**: Async web service with an operator CLI

**Performance Goals**: Startup verification performs bounded collection/index metadata reads only; no collection data scan

**Constraints**: Application startup cannot mutate shared schema; bootstrap must be idempotent under concurrent release actors; diagnostics cannot expose URIs, credentials, or records

**Scale/Scope**: Four Mongo collections and one schema-state collection at schema version 1

## Constitution Check

*GATE: Passed before research and rechecked after design.*

- **Canonical truth**: PASS — Mongo remains the only authoritative event store.
- **At-least-once safety**: PASS — verification requires the unique `event_id` index before the persistence worker starts.
- **Async correctness**: PASS — bootstrap and verification use PyMongo's async API and bounded driver timeouts.
- **Lifecycle ownership**: PASS — the application-owned client is verified before worker/task startup and closed by the existing lifespan supervisor.
- **Security**: PASS — structured diagnostics contain operation/classification fields only; no URI, credential, index contents, or documents.
- **Testing**: PASS — unit failure classification and real-Mongo empty/incompatible storage scenarios are planned.
- **Simplicity**: PASS — one manifest and one bootstrap service are used; no migration framework or speculative compound indexes are introduced.

## Design

1. `storage/bootstrap.py` owns immutable collection names, index declarations, schema version compatibility, bootstrap, and verification.
2. Event index definitions continue to come from `storage/mongo.py`; the manifest reuses them rather than creating a second list.
3. Checkpoint lookup gets one unique `projector` index. Rebuild history gets unique `rebuild_id` and descending `started_at` indexes. The lease collection's built-in `_id_` index is declared and verified because lease acquisition is keyed by its fixed `_id`.
4. Bootstrap creates required indexes, then atomically inserts the versioned schema marker with `$setOnInsert`; concurrent actors converge on the same immutable manifest fingerprint and verify the final state.
5. Verification reads the schema marker and index metadata, rejecting missing, newer, older, or structurally incompatible state with a safe typed error.
6. `event_platform.cli storage bootstrap|verify` owns release-time mutation and operator verification. The application lifespan calls verification only when it owns a configured Mongo client.
7. `ServiceSettings` rejects production without `mongo_url` before any runtime client is created.
8. Compose adds a one-shot `storage-bootstrap` service between `mongo-init` and `app`.

## Project Structure

### Documentation (this feature)

```text
specs/026-ACR1_storage-bootstrap-integrity/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── storage-schema.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/event_platform/
├── cli.py
├── core/settings.py
├── main.py
└── storage/
    ├── bootstrap.py
    ├── checkpoints.py
    ├── mongo.py
    └── rebuilds.py

tests/
├── unit/
│   ├── test_app_lifecycle.py
│   ├── test_app_settings.py
│   ├── test_storage_bootstrap.py
│   └── test_storage_bootstrap_cli.py
└── integration/
    └── test_storage_bootstrap_integration.py
```

**Structure Decision**: Extend the existing storage adapter, application lifespan, CLI, and test packages. Keep the schema boundary in `storage/bootstrap.py` so API routes and workers do not acquire migration responsibilities.

## Post-Design Constitution Check

All pre-design gates remain PASS. The design adds no authoritative derived store, synchronous network I/O, unbounded scan, new queue guarantee, or architecture exception.

## Complexity Tracking

No constitution violations require justification.
