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
- **Validation/review performed:** focused tests passed 21/21; Ruff format/lint and mypy passed after correction. Full Makefile and manual quickstart validation are the final Feature 001 gate.
