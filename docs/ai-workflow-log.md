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
