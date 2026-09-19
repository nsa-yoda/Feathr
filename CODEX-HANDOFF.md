# Codex Final Handoff — Distributed Event Processing Platform

## Mission

Build the complete repository described by this handoff as a production-grade, enterprise-quality backend assessment submission. The implementation must satisfy every requirement from the supplied assessment **and** the additional reviewer-experience and operational requirements in this pack.

This handoff is intentionally opinionated. Architectural decisions marked **LOCKED** are already decided and must not be casually redesigned by Codex. Implementation-level choices may be refined when necessary, but any change to a locked decision requires:

1. a written ADR that supersedes the existing ADR,
2. an explicit reason grounded in correctness or feasibility,
3. corresponding updates to `ARCHITECTURE.md`, affected feature artifacts, tests, and requirements traceability,
4. a review pass that specifically evaluates the change.

The desired result is not a toy take-home. It should look like a compact but credible enterprise service that a principal engineer could defend in a design review.

## Non-negotiable workflow

Use Spec Kit for every implementation feature. Do not skip directly from these documents to coding.

### Bootstrap Spec Kit for Codex

Run from the repository root:

```bash
./scripts/bootstrap-speckit.sh
```

The script preserves this project's hand-authored constitution, initializes Spec Kit for the `codex` integration when necessary, and installs the two mandatory review extensions.

Codex-native Spec Kit skills use `$speckit-...` syntax. The full production workflow for each feature is:

```text
$speckit-specify
      ↓
$speckit-clarify
      ↓
$speckit-plan
      ↓
$speckit-checklist
      ↓
$speckit-tasks
      ↓
$speckit-analyze
      ↓
$speckit-implement
      ↓
$speckit-converge
      ↓
repeat implement/converge until clean
      ↓
$speckit-staff-review-run
      ↓
$speckit-review-run all
      ↓
remediate all blockers/critical findings
      ↓
targeted re-review
      ↓
feature acceptance
```

Do not mark a feature complete merely because code exists. The acceptance gate is defined in `docs/definition-of-done.md`.

## Feature execution order

Read `specs/FEATURE-MANIFEST.yaml`. Execute features in dependency order. The request documents under `specs/NNN-*/REQUEST.md` are **inputs** to `$speckit-specify`; they are not substitutes for generated `spec.md`, `plan.md`, `tasks.md`, and checklists.

For each feature:

1. Read the feature's `REQUEST.md` completely.
2. Read all linked ADRs and architecture documents.
3. Invoke `$speckit-specify` using the request as the authoritative feature request.
4. Invoke `$speckit-clarify`. Resolve every material ambiguity. Never silently guess a queue, consistency, retry, cache, pagination, security, or failure semantic.
5. Invoke `$speckit-plan`. Plans must preserve locked architecture.
6. Invoke `$speckit-checklist` with emphasis on correctness, failure behavior, observability, security, and tests.
7. Invoke `$speckit-tasks`.
8. Invoke `$speckit-analyze`. Do not implement while critical contradictions remain.
9. Invoke `$speckit-implement`.
10. Run relevant tests and quality gates.
11. Invoke `$speckit-converge`. If tasks are appended, implement and converge again until clean.
12. Run the staff review extension and the six-agent review extension.
13. Remediate findings and rerun targeted reviews.
14. Update `docs/ai-workflow-log.md` with important AI contributions, corrections, and human decisions.
15. Update requirements traceability where implementation/test evidence now exists.

## Locked architectural decisions

The following are fixed unless superseded by an explicit ADR:

- FastAPI, Pydantic v2, Python 3.12+, async I/O.
- PyMongo Async API (`pymongo.AsyncMongoClient`), not Motor.
- MongoDB is the canonical source of event truth.
- Elasticsearch is a rebuildable, eventually consistent search projection.
- Redis is non-authoritative. It provides realtime-stat caching and distributed rate-limit state; the service degrades without it.
- Ingestion uses an in-process SQS-style queue because the assessment explicitly requires a simulated in-process queue.
- The demo runtime therefore uses **one application process**. Multiple API processes would create independent queues and violate the intended semantics.
- The in-process queue models at-least-once delivery while the process is alive, with visibility timeout, receipt handles, retry/backoff, bounded capacity, and a simulated DLQ.
- `POST /events` returns `202 Accepted` only after validation and successful enqueue into the local queue. In the demo this is **not crash-durable**. The architecture must say so plainly.
- The persistence worker acknowledges/deletes a queue message only after MongoDB has durably accepted the canonical event, or after an idempotent replay is confirmed equivalent.
- Worker redelivery is made safe by an immutable `event_id` with a unique MongoDB index.
- Elasticsearch projection does not participate in the ingestion acknowledgement path.
- MongoDB Change Streams drive the normal live Elasticsearch projection. Docker Compose runs MongoDB as a single-node replica set so change streams work locally.
- Elasticsearch writes use a stable alias and immutable/versioned backing indices.
- Elasticsearch rebuilds are online: create a new generation, mark rebuild active, bulk-project Mongo, dual-write live change-stream events into the rebuild target, verify/catch up, atomically swap the alias, retain the prior generation temporarily, and log the complete lifecycle.
- Search projection uses the event's immutable `event_id` as the Elasticsearch document `_id`, making replays idempotent.
- Flexible metadata must not cause Elasticsearch mapping explosion. Store the JSON in a `flattened` field and separately derive a `metadata_text` full-text field.
- Redis realtime statistics use cache-aside semantics. Cache failures never lose events.
- **Rate limiting is mandatory.** Use a Redis-backed atomic leaky bucket that reserves bounded release slots and asynchronously queues ordinary bursts. Use a conservative process-local leaky-bucket fallback when Redis is unavailable. Return `429` only when the bounded admission backlog is full; degraded limiting and queued/overflow decisions must be observable.
- Do not trust `X-Forwarded-For` unless trusted proxy configuration explicitly enables it.
- Mongo event queries use cursor/keyset pagination, not unbounded offset pagination.
- API errors use a consistent RFC 9457-style `application/problem+json` shape.
- Structured JSON logging, request/correlation IDs, Prometheus-compatible metrics, liveness/readiness/component health, graceful shutdown, and explicit degraded states are mandatory.
- Docker Compose must start the API, MongoDB replica set, Elasticsearch, Redis, and demo UI with one normal reviewer command.
- The UI is a reviewer/demo console only. It must not compromise backend scope or become a second product.
- A Postman collection plus local environment is mandatory and should function as an external reviewer acceptance suite, not merely a saved-request list.
- Tests must use real MongoDB/Elasticsearch/Redis in integration coverage; mocks alone are insufficient.

## Scope discipline

Do not add unrelated product features. In particular, do not spend time on end-user authentication, user accounts, billing, frontend design systems, GraphQL, Kafka, Kubernetes, or cloud provisioning. Production evolution belongs in architecture notes, not speculative code.

## Final submission quality bar

Before finalizing:

- all mandatory assessment requirements are demonstrably implemented;
- all bonus items selected in this handoff are implemented: Docker Compose, rate limiting, worker deduplication, DLQ simulation, and SQS migration notes;
- `docker compose up --build` reaches healthy state without manual service-by-service setup;
- the UI is usable at the documented URL;
- Postman collection runner succeeds against the Compose stack;
- unit, integration, failure-path, lint, formatting, and type checks pass;
- architecture and README describe the implementation as it actually exists;
- no architecture document falsely claims guarantees the in-process queue cannot provide;
- no secrets or credentials are committed other than clearly marked local-development defaults in `.env.example`;
- no unresolved Blocker/Critical review findings remain;
- important warnings are either fixed or documented with rationale;
- `AI in My Workflow` is factual and derived from the maintained AI workflow log.
