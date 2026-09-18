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
