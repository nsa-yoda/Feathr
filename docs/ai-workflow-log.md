# AI Workflow Decision Log

Maintain this throughout implementation. The final README `AI in My Workflow` section must be synthesized from real entries here, not generic prose.

## Entry template

### YYYY-MM-DD — <topic>

- **Tool/model:**
- **Task:**
- **AI proposal/contribution:**
- **What was useful:**
- **Pushback/correction:**
- **Human decision and rationale:**
- **Artifacts/code affected:**
- **Validation/review performed:**

---

## Seed decisions made during architecture work

### 2026-09-18 — Canonical versus derived stores

- **Tool/model:** ChatGPT GPT-5.6 Sol
- **Task:** stress-test Mongo/Elasticsearch/Redis ownership.
- **AI proposal/contribution:** separate Mongo canonical persistence from ES and Redis; avoid dual-write transaction semantics.
- **What was useful:** clarified partial-failure behavior and made ES rebuildability a first-class property.
- **Pushback/correction:** reviewer insisted rebuildability be seamless and explicitly logged, not just theoretically possible.
- **Human decision and rationale:** Mongo is canonical; ES uses an online alias-based rebuild; Redis is non-authoritative.
- **Artifacts/code affected:** ARCHITECTURE.md, ADRs 0003/0007/0008.

### 2026-09-18 — Rate limiting scope

- **Tool/model:** ChatGPT GPT-5.6 Sol
- **Task:** classify optional bonus features.
- **AI proposal/contribution:** initially described rate limiting conditionally.
- **Pushback/correction:** human explicitly rejected treating rate limiting as optional.
- **Human decision and rationale:** rate limiting is mandatory and implemented with Redis token bucket plus local fallback.
- **Artifacts/code affected:** constitution, ADR-0009, Feature 015.

### 2026-09-18 — Reviewer experience

- **Tool/model:** ChatGPT GPT-5.6 Sol
- **Task:** decide whether to add unscored UI and Postman assets.
- **AI proposal/contribution:** frame them as reviewer/operator surfaces rather than product scope.
- **Pushback/correction:** human emphasized both should ship by default in Compose/repository.
- **Human decision and rationale:** lightweight UI and executable Postman suite are mandatory value-adds, without sacrificing backend work.
- **Artifacts/code affected:** ADR-0015, Features 023/024.

### 2026-09-18 — Platform foundation planning and implementation

- **Tool/model:** Codex with Spec Kit and Serena MCP.
- **Task:** turn Feature 001's accepted request into a plan, dependency-ordered tasks, a runnable FastAPI foundation, and test evidence.
- **AI proposal/contribution:** drafted the spec, design artifacts, contract, checklists, tasks, package boundaries, typed settings, lifespan, liveness, request IDs, and safe problem responses; wrote story tests before corresponding behavior.
- **What was useful:** the cross-artifact check found that degraded dependency behavior and broader runtime JSON logging needed explicit deferral to later features. The tests exposed missing route/error behavior before implementation; the later staff review correctly required foundation lifecycle/error logging before acceptance.
- **Pushback/correction:** mypy rejected the initial exception handler signatures; the handler annotations were corrected before committing. The machine's configured GPG signer failed, so the first verified commit used a command-local unsigned override, recorded in `CODEX_WORK.LOG`.
- **Human decision and rationale:** the user required timestamped work logging, heavy Serena use, and commits as coherent work slices. Feature 001 preserves a narrow foundation scope so liveness cannot be read as datastore readiness.
- **Artifacts/code affected:** `specs/001-platform-foundation/`, `src/event_platform/`, `tests/unit/`, `README.md`, `docs/api-contract.md`, and `CODEX_WORK.LOG`.
- **Validation/review performed:** focused tests passed 26/26; Ruff format/lint and mypy passed after correction. Full Makefile and manual quickstart validation are the final Feature 001 gate.

### 2026-09-18 — Review gate remediation and merge preparation

- **Tool/model:** Codex with Spec Kit review extensions and Serena MCP.
- **Task:** resolve fresh staff/comprehensive review findings before moving Feature 001 to the merge gate.
- **AI proposal/contribution:** configured Uvicorn with checked-in JSON startup/access logging, removed query strings from access records, added `.env` loading and sanitized startup field context, strengthened problem response types, and expanded lifecycle/process/request-ID regression coverage.
- **What was useful:** the subprocess smoke test exposed that application startup reconfigured the Uvicorn access handler back to a generic formatter; keeping a dedicated access formatter after lifespan configuration closed that runtime gap.
- **Pushback/correction:** review evidence was updated from 21 to the current 26 unit tests, while historical work-log entries remain unchanged as historical records.
- **Human decision and rationale:** accept only after actual subprocess output is parsed as JSON, lifecycle events are present, query secrets are absent, and all repository quality targets pass.
- **Artifacts/code affected:** `src/event_platform/core/logging.py`, `src/event_platform/core/uvicorn_logging.json`, `src/event_platform/core/settings.py`, `src/event_platform/api/problems.py`, `src/event_platform/main.py`, unit tests, traceability, and Feature 001 review artifacts.
- **Validation/review performed:** Ruff format/lint, strict mypy, 26 unit tests, and empty-safe integration/failure suites passed; the subprocess smoke test passed with reserved-socket startup, event names on every JSON record, and redacted access logging.

### 2026-09-18 — Event domain contract implementation and review

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** specify, plan, implement, converge, and review Feature 002 before persistence and ingestion features.
- **AI proposal/contribution:** drafted a bounded Pydantic event input contract, recursive metadata validation, UTC normalization, immutable canonical events, deterministic compact JSON, and SHA-256 payload/idempotency hashes; used Serena search and symbol inspection to verify ownership boundaries and documentation consistency.
- **What was useful:** boundary-first tests exposed Pydantic tuple coercion and shallow nested mutability; review also required direct-construction UTC enforcement and secret-safe extra-field diagnostics.
- **Pushback/correction:** numeric limits, control-character rules, empty-key behavior, non-JSON rejection, and the no-latency-SLO position were made explicit in every affected design artifact after review found documentation drift.
- **Human decision and rationale:** keep Feature 002 pure and infrastructure-free so storage, queue, and HTTP mappings remain dependent features; accept only after focused and full quality gates plus staff/comprehensive review.
- **Artifacts/code affected:** `specs/002-event-domain-contract/`, `src/event_platform/domain/events.py`, `tests/unit/test_event_domain.py`, `docs/requirements-traceability.md`, and `CODEX_WORK.LOG`.
- **Validation/review performed:** focused domain tests (27), full unit regression, Ruff format/lint, strict mypy, empty-safe integration/failure suites, and review remediation with no remaining blockers.

### 2026-09-18 — MongoDB store and index contract implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** implement Feature 003's canonical async persistence/query boundary and required indexes after Features 001 and 002 were accepted.
- **AI proposal/contribution:** defined typed query values, BSON mapping, PyMongo Async repository operations, deterministic `IndexModel` definitions, duplicate/dependency error translation, and a real-Mongo integration path gated by `MONGO_URI`.
- **What was useful:** the boundary tests caught a test-module naming collision and verified the repository never exposes raw driver exception text; lock metadata was updated from PyPI because the host `uv` binary panics in its system-configuration layer.
- **Pushback/correction:** foundation startup remains Mongo-independent; explicit index bootstrap is the accepted lifecycle boundary until a later feature wires configured clients into the app lifespan.
- **Human decision and rationale:** store event IDs as lowercase strings for portable API/Mongo/projection identity, keep pagination's opaque cursor encoding in the API layer, and omit metadata/wildcard indexes per ADR-0010.
- **Artifacts/code affected:** `specs/003-mongodb-store-indexes/`, `src/event_platform/storage/`, `tests/unit/test_mongo_store.py`, `tests/integration/test_mongo_store_integration.py`, `pyproject.toml`, `uv.lock`, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** Feature 003 storage tests pass 9/9 and the real replica-set integration test passes with a temporary MongoDB 8 container; full unit suite, Ruff, and strict mypy are rerun before commit. The host `uv lock --check` remains unavailable because uv panics in the macOS system-configuration layer.

### 2026-09-18 — In-process SQS-style queue implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** implement the bounded local queue required by the queue semantics constitution before ingestion API work.
- **AI proposal/contribution:** used `asyncio.Condition`, an injectable monotonic clock, recursively frozen bodies, per-delivery receipt UUIDs, visibility expiry, bounded sends, close wakeups, stats, and DLQ redrive.
- **What was useful:** deterministic clock advancement plus a wake hook made expiry/redelivery tests fast and avoided arbitrary sleeps; tests cover stale receipts and concurrent consumers.
- **Pushback/correction:** the queue remains independent of Mongo and HTTP; no fake distributed durability or exactly-once claim was introduced.
- **Human decision and rationale:** capacity includes in-flight messages, receipt handles rotate on every receive, and delete remains valid for an already returned delivery after queue close.
- **Artifacts/code affected:** `specs/004-inprocess-sqs-queue/`, `src/event_platform/queue/`, `tests/unit/test_in_process_queue.py`, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** queue tests pass 6/6; full unit suite passes 68 tests with two existing dependency warnings; Ruff and strict mypy pass; integration/failure marker suites are empty-safe.

### 2026-09-18 — Async ingestion API implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** connect Feature 002 canonical events to the Feature 004 queue through `POST /events`.
- **AI proposal/contribution:** added bounded queue settings/lifespan ownership, a typed FastAPI route, hash-only idempotency header handling, 202 queued responses, safe 503 backpressure, and OpenAPI response declarations.
- **What was useful:** route tests verify that request IDs remain server-owned, validation uses the existing problem contract, and queue saturation cannot return a false 202.
- **Pushback/correction:** Mongo is deliberately absent from the request path; durable duplicate semantics remain Feature 006 as required by the request.
- **Human decision and rationale:** use the queue body as a JSON canonical envelope and close the queue during application shutdown so ownership is explicit within process lifetime.
- **Artifacts/code affected:** `specs/005-ingestion-api/`, `src/event_platform/api/routes/events.py`, `src/event_platform/core/settings.py`, `src/event_platform/main.py`, and `tests/unit/test_ingestion_api.py`.
- **Validation/review performed:** focused ingestion tests pass 5/5; full unit suite passes 73 tests with two existing dependency warnings; Ruff and strict mypy pass; integration/failure marker suites are empty-safe.

### 2026-09-18 — Persistence worker and idempotency implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** consume Feature 005 canonical envelopes, persist them through the Feature 003 Mongo boundary, and acknowledge only after durable insert or verified same-hash duplicate handling.
- **AI proposal/contribution:** added a bounded-concurrency async worker with immutable metrics, explicit decode/dependency/conflict classifications, a conflict disposition hook, and crash-safe redelivery semantics.
- **What was useful:** fake-store tests made the ack boundary, same-hash verification, conflicting event behavior, and concurrency limit deterministic; the temporary MongoDB 8 replica-set run verified the duplicate path against the real async repository.
- **Pushback/correction:** no overwrite or implicit conflict resolution was introduced. Conflicting event IDs remain unacknowledged unless a later policy hook explicitly accepts the disposition, and DLQ policy remains Feature 007.
- **Human decision and rationale:** keep this worker independent of HTTP lifecycle wiring until the later worker-runtime feature, while exposing a reusable `run()` loop for bounded consumers.
- **Artifacts/code affected:** `specs/006-persistence-worker-idempotency/`, `src/event_platform/worker/`, `tests/unit/test_persistence_worker.py`, `tests/integration/test_persistence_worker_integration.py`, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** focused worker tests pass 5/5; full unit suite passes 78 tests with two existing upstream dependency warnings; real MongoDB 8 replica-set integration passes 1/1; Ruff format/lint, strict mypy, and empty-safe failure/integration marker suites pass.

### 2026-09-18 — Retry, backoff, and simulated DLQ implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** make every Feature 006 persistence failure explicit through bounded visibility retry, permanent/unknown classification, and a volatile simulated DLQ.
- **AI proposal/contribution:** added `RetryPolicy` with injectable jitter, stable safe reason codes, targeted queue dead-lettering, oldest-age statistics, and immutable retry/DLQ metrics.
- **What was useful:** deterministic clocks and injected jitter made exponential-delay bounds and no-sleep worker behavior directly testable; queue tests caught the need to preserve the existing `dlq()` delivery view while adding diagnostic entries.
- **Pushback/correction:** an initial default retry delay changed a Feature 006 immediate-redelivery test; the test was corrected to advance an injected clock, preserving the production backoff contract without arbitrary sleeps. Raw exception text was deliberately excluded from DLQ diagnostics.
- **Human decision and rationale:** attempt 1 is the first receive, default maximum receives is 5, permanent validation/conflict failures bypass retry, and unknown failures receive only bounded retry before DLQ.
- **Artifacts/code affected:** `specs/007-retry-backoff-dlq/`, `src/event_platform/queue/`, `src/event_platform/worker/`, queue/worker tests, queue/failure architecture docs, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** initial focused Feature 007 and regression pass was 18 tests; after review remediation the focused queue/worker set passes 36 tests. The full unit suite passes 103 tests with two existing upstream dependency warnings; integration/failure marker suites are empty-safe; final review evidence is recorded in the Feature 007 review report before commit.

### 2026-09-18 — Event query API implementation and review preparation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** implement Feature 008's canonical filtered event query with safe keyset pagination.
- **AI proposal/contribution:** added a typed FastAPI `GET /events` route, filter-bound HMAC cursor codec, canonical Mongo store boundary, page metadata, dependency-safe problem responses, and a fake-store behavior suite.
- **What was useful:** equal-timestamp traversal tests and tamper tests exposed the need for an exclusive `(timestamp,event_id)` continuation and canonical base64 validation; binding the signature to active filters closes cursor scope drift without putting query data in the token.
- **Pushback/correction:** the initial implementation treated a changed final base64 character as valid due unused base64 bits and used an assertion that confused `event_id` with Mongo `_id`; both were corrected before review.
- **Human decision and rationale:** keep Mongo client lifecycle ownership in the later application lifecycle feature, so a missing store is an explicit safe 503 while Feature 008 remains independently testable.
- **Artifacts/code affected:** `specs/008-event-query-api/`, `src/event_platform/api/routes/query.py`, `src/event_platform/main.py`, `tests/unit/test_event_query_api.py`, `docs/api-contract.md`, and `docs/requirements-traceability.md`.
- **Validation/review performed:** focused query suite passed 31 tests after adding normalized URL, malformed cursor shape, decode-failure, and bounded filter cases; Ruff format/lint and strict mypy passed. Full unit, integration/failure marker, convergence, staff, and comprehensive review gates remain to be recorded before commit.

### 2026-09-18 — Feature 008 review gate and merge preparation

- **Tool/model:** Codex with staff/comprehensive Spec Kit review procedures, Serena MCP, and specialized review agents.
- **Task:** move the Event Query API through convergence, review, and final quality gates.
- **AI proposal/contribution:** reviewed the route against all ten functional requirements, checked cursor security and filter scope, and produced the feature-local staff review report.
- **What was useful:** specialized review caught equivalent source URL cursor scope drift and missing malformed-input regressions; both were corrected before approval.
- **Pushback/correction:** review evidence was held pending the actual report and final full-suite rerun; task T010 remained open until those artifacts existed.
- **Human decision and rationale:** approve the feature with one non-blocking suggestion to add a live Mongo route test after lifecycle ownership is implemented; keep the current fake-store test boundary for this feature.
- **Artifacts/code affected:** `specs/008-event-query-api/reviews/review-20260918-203000.md`, tasks, traceability, and the final gate records.
- **Validation/review performed:** 31 focused tests passed; full unit suite passed 134 tests with two existing dependency warnings; integration markers skipped 2 without external services; failure marker selection was empty-safe; Ruff format/lint, strict mypy, and diff check passed.

### 2026-09-18 — MongoDB analytics implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** specify and implement bounded canonical MongoDB statistics for hour/day/week buckets.
- **AI proposal/contribution:** defined a UTC-only inclusive range contract, previous-24-hour default, Monday week semantics, typed response points, early `$match`, `$dateTrunc` grouping, stable sorting, and unit/real-Mongo test boundaries.
- **What was useful:** separating effective-range validation from pipeline construction made default-window behavior deterministic and let tests assert the exact aggregation shape without loading raw events.
- **Pushback/correction:** raw Python aggregation was rejected by the request and constitution; the route delegates all grouping to `MongoEventStore.aggregate` and maps malformed documents to the safe dependency boundary.
- **Human decision and rationale:** keep client lifecycle ownership deferred, so the route returns a retryable 503 when `app.state.event_store` is unavailable while remaining independently testable.
- **Artifacts/code affected:** `specs/009-mongodb-analytics/`, `src/event_platform/api/routes/stats.py`, `src/event_platform/main.py`, `tests/unit/test_mongodb_analytics.py`, `tests/integration/test_mongodb_analytics_integration.py`, and documentation.
- **Validation/review performed:** focused analytics tests pass 21/21; real Mongo integration is present and runs when `MONGO_URI` is configured; Ruff and strict mypy pass.

### 2026-09-18 — Feature 009 review gate and merge preparation

- **Tool/model:** Codex with staff/comprehensive Spec Kit review procedures, Serena MCP, and specialized review agents.
- **Task:** move MongoDB analytics through convergence, review, and final quality gates.
- **AI proposal/contribution:** reviewed the aggregation route, canonical storage boundary, UTC BSON decoding, result cardinality, and execution lifetime against the Feature 009 contract.
- **What was useful:** review caught that the response point cap alone did not bound a high-cardinality Mongo operation; the typed repository now passes a finite `maxTimeMS` deadline while the route still rejects oversized results without partial counts.
- **Pushback/correction:** naive BSON timestamps, same-bucket ordering, exact inclusive endpoints, safe error envelopes, and stale test-count records were corrected before approval.
- **Human decision and rationale:** keep Mongo client lifecycle ownership deferred to the later lifecycle feature; a missing store remains a safe retryable 503, while the direct real-Mongo aggregation path is covered here.
- **Artifacts/code affected:** `specs/009-mongodb-analytics/reviews/`, `src/event_platform/api/routes/stats.py`, `src/event_platform/storage/mongo.py`, analytics and storage tests, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** 21 focused analytics tests, 30 analytics/storage tests, 155 full unit tests, 3 real-Mongo integration tests, and empty-safe failure selection passed; Ruff format/lint, strict mypy, and diff checks passed. Review findings: 0 blockers, 0 warnings, 0 suggestions after remediation.

### 2026-09-18 — Mongo change-stream search projection implementation

- **Tool/model:** Codex with Spec Kit workflows and Serena MCP.
- **Task:** specify and implement Feature 010's replay-safe Mongo-to-Elasticsearch projection boundary.
- **AI proposal/contribution:** added explicit async ports for deterministic projection, Elasticsearch alias/target writes, Mongo checkpoints, and insert-only change streams; the coordinator persists checkpoints only after all required writes succeed.
- **What was useful:** keeping resume tokens inside the checkpoint boundary made invalid-history handling and sensitive-token redaction testable without coupling the API to driver details.
- **Pushback/correction:** Elasticsearch remains derived and outside ingestion acknowledgement; invalid resume history enters reconciliation-required state instead of silently starting at the current position, and replay uses immutable event IDs.
- **Human decision and rationale:** Feature 012 owns online rebuild orchestration; Feature 010 exposes an optional target-generation write seam without implementing alias swaps or bulk rebuild.
- **Artifacts/code affected:** `specs/010-search-projection-changestream/`, `src/event_platform/search/`, `src/event_platform/storage/checkpoints.py`, `src/event_platform/storage/change_stream.py`, tests, dependency lock files, architecture, traceability, and `CODEX_WORK.LOG`.
- **Validation/review performed:** 26 focused projection unit tests and 2 failure tests pass; the real-service integration selection explicitly skips one test without MongoDB/Elasticsearch. The full unit suite passes 181 tests with two existing dependency deprecation warnings; Ruff format/lint, strict mypy, and diff checks pass. Final review report: `specs/010-search-projection-changestream/reviews/review-20260918-211700.md`.
