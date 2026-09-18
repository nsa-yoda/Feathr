# Requirements Traceability Matrix

This file starts as a planning matrix. Codex must update the final two columns with concrete source/test evidence as implementation lands.

| Requirement | Feature(s) | Planned evidence | Implementation evidence | Test evidence |
|---|---|---|---|---|
| POST /events validates and enqueues asynchronously | 002, 004, 005 | API spec + queue contract | TBD | TBD |
| Background worker persists Mongo | 005, 006 | worker/repository | TBD; Feature 003 provides `src/event_platform/storage/mongo.py` primitives | Feature 003 unit mapping/error coverage; real-Mongo integration is environment-gated |
| Retry with backoff | 007 | retry policy | TBD | TBD |
| GET /events filters | 009 | query service | TBD | TBD |
| GET /events/stats aggregation | 010 | Mongo pipeline | TBD | TBD |
| GET /events/search metadata full-text | 011, 012 | ES projection/search | TBD | TBD |
| GET /events/stats/realtime Redis cache | 014 | cache-aside service | TBD | TBD |
| Mongo indexes | 003 | index bootstrap | `src/event_platform/storage/mongo.py` `REQUIRED_INDEXES`, `index_models`, and `MongoEventStore.ensure_indexes` | `tests/unit/test_mongo_store.py`; `tests/integration/test_mongo_store_integration.py` |
| Mongo canonical repository | 003 | async insert/fetch/query/aggregate boundary | `src/event_platform/storage/mongo.py` `MongoEventStore`, typed `EventQuery`, BSON mapping, and safe errors | `tests/unit/test_mongo_store.py` (9 tests); `tests/integration/test_mongo_store_integration.py` (real replica-set pass) |
| ES mapping/analyzers | 012 | versioned mapping | TBD | TBD |
| ARCHITECTURE.md standalone | 025 | root architecture | `ARCHITECTURE.md` | doc review |
| Failure modes | 005, 011, 014, 016, 021, 025 | failure docs/tests | TBD | TBD |
| Scaling considerations | 025 | architecture | `ARCHITECTURE.md` | doc review |
| What changes in production | 004, 013, 025 | SQS/rebuild/scaling docs | TBD | doc review |
| Unit tests | all + 019 | per-feature tests | Feature 001: `tests/unit/` and `pyproject.toml` markers | Feature 001: `make test-unit` (26 tests); remaining features TBD |
| 2+ integration lifecycles | 020 | real-service tests | TBD | TBD |
| Clear module boundaries | 001 | package architecture | `src/event_platform/` package boundaries and `src/event_platform/main.py` app factory | `tests/unit/test_import_safety.py`; source review |
| Event input validation and canonical hashing | 002 | `specs/002-event-domain-contract/spec.md`, `contracts/domain.md` | `src/event_platform/domain/events.py` (`EventInput`, `CanonicalEvent`, `canonical_payload`, `payload_hash`) | `tests/unit/test_event_domain.py` (27 tests; all boundaries, redaction, immutability, and hash stability) |
| SQS-style local queue semantics | 004 | `specs/004-inprocess-sqs-queue/spec.md`, `contracts/queue.md` | `src/event_platform/queue/in_process.py` (`InProcessQueue`, receipts, visibility, redrive, stats) | `tests/unit/test_in_process_queue.py` (6 deterministic concurrency/semantics tests) |
| Foundation lifecycle, configuration, and liveness | 001 | foundation spec and HTTP contract | `src/event_platform/main.py`, `core/settings.py`, `api/routes/health.py`, `.env.example` | `tests/unit/test_app_lifecycle.py`, `test_app_settings.py`, `test_settings.py` |
| Foundation problem responses and request IDs | 001 | foundation HTTP contract | `src/event_platform/api/problems.py`, `api/middleware/request_id.py` | `tests/unit/test_problems.py`, `test_request_id.py` |
| Meaningful error handling/logging | 016, 018 | problem+json + JSON logs | Feature 001 safe problem responses plus structured lifecycle/error logging in `src/event_platform/api/problems.py`, `src/event_platform/core/logging.py`, and `src/event_platform/main.py`; broader dependency-operation logging TBD | Feature 001 `tests/unit/test_problems.py`, `test_app_lifecycle.py`, and `test_app_settings.py`; later features TBD |
| AI in My Workflow | 025 | maintained workflow log | TBD | doc review |
| Dockerfile/docker-compose bonus | 022 | full stack | TBD | smoke |
| Rate limiting bonus (mandatory here) | 015 | distributed + fallback limiter | TBD | TBD |
| Event deduplication bonus | 006 | unique ID/payload hash | TBD | TBD |
| DLQ simulation bonus | 007 | local redrive | TBD | TBD |
| AWS SQS drop-in notes | 004, 025 | port + design notes | TBD | doc review |
| Reviewer UI value-add | 024 | Compose UI | TBD | browser/smoke |
| Postman reviewer suite value-add | 023 | collection/environment | TBD | Newman/Postman run |
