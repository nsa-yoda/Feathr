# Architecture — Distributed Event Processing Platform

## 1. Executive summary

The platform accepts high-volume web events over HTTP, validates and asynchronously persists them to MongoDB, serves canonical queries and aggregations from MongoDB, projects searchable representations into Elasticsearch, and caches a lightweight realtime statistics view in Redis.

The design intentionally distinguishes **canonical state** from **derived state**:

- **MongoDB:** authoritative event record.
- **Elasticsearch:** eventually consistent, rebuildable search projection.
- **Redis:** disposable/derived cache plus distributed rate-limit coordination.
- **In-process queue:** assessment-mandated simulation of SQS semantics; useful for demonstrating retry/visibility behavior but intentionally not crash-durable.

The demo runs as a single FastAPI process because an in-process queue cannot be shared safely across multiple application processes. A production SQS implementation removes that constraint and separates horizontally scalable API and worker fleets.

Security hardening is enforced at the HTTP receive/configuration boundary: body
bytes are bounded before JSON parsing, typed query and cursor contracts remain
strict, CORS uses one configured origin, forwarded identity is opt-in, and
normal responses/logs are sanitized. The API and reviewer UI images use
non-root runtime users; local Elasticsearch authentication is intentionally a
Compose-only convenience documented as such.

## 2. System diagram

```text
                              ┌───────────────────────────┐
                              │        Demo UI            │
                              │ static reviewer console + nginx  │
                              └─────────────┬─────────────┘
                                            │ HTTP
                                            ▼
┌───────────────┐                  ┌─────────────────────────────┐
│ Postman/Users │ ───────────────► │ FastAPI Application         │
└───────────────┘                  │                             │
                                   │  validation                 │
                                   │  request IDs                │
                                   │  rate limiting              │
                                   │  query/search/cache routes  │
                                   └──────┬───────────┬──────────┘
                                          │           │
                          POST /events    │           │ reads
                                          ▼           │
                                  ┌──────────────┐    │
                                  │ In-process   │    │
                                  │ SQS-like     │    │
                                  │ queue        │    │
                                  └──────┬───────┘    │
                                         │ receive    │
                                         ▼            │
                                  ┌──────────────┐    │
                                  │ Persistence  │    │
                                  │ worker       │    │
                                  └──────┬───────┘    │
                                         │            │
                                         ▼            ▼
                              ┌─────────────────────────────┐
                              │ MongoDB replica set         │
                              │ CANONICAL EVENT STATE       │
                              └──────┬──────────────────────┘
                                     │ change stream
                                     ▼
                              ┌───────────────────────┐
                              │ Search projector      │
                              │ checkpointed consumer │
                              └──────────┬────────────┘
                                         │
                                         ▼
                              ┌─────────────────────────────┐
                              │ Elasticsearch                │
                              │ events-search alias          │
                              │ DERIVED SEARCH PROJECTION    │
                              └─────────────────────────────┘

FastAPI ───────── cache-aside ──────────────► Redis
       └──────── distributed rate limit ────► Redis
       └──────── local limiter fallback if Redis unavailable
```

## 3. Request/ingestion lifecycle

1. `POST /events` receives JSON.
2. Middleware assigns or validates a request ID and enforces body-size/rate limits.
3. Pydantic validates the event contract and normalizes timestamp/URL fields.
4. The service assigns an immutable `event_id`; optional `Idempotency-Key` influences deterministic duplicate handling as specified in Feature 007.
5. A scoped idempotency reservation uses an owner token and generation. Queue admission
   failure releases only that owner; successful admission transitions the record to
   `enqueued`, and stale takeover uses an atomic Mongo compare-and-set.
6. An envelope is offered to the bounded SQS-like in-process queue.
7. If enqueue succeeds, API returns `202 Accepted` with `event_id`, `status=queued`, and request ID.
8. If the queue is saturated beyond the configured enqueue timeout, API returns `503 Service Unavailable` with `Retry-After` and releases the reservation.
9. The persistence worker receives a message and a receipt handle. The message becomes invisible for the visibility timeout.
10. The worker inserts the canonical event into MongoDB. Unique `event_id` provides idempotent redelivery behavior.
11. Only after Mongo accepts the event (or an equivalent duplicate is verified) does the worker delete/ack the queue message.
12. Retryable failures use bounded exponential backoff with jitter and adjusted visibility. Exhausted messages move to the simulated DLQ.
13. Mongo's event Change Stream asynchronously projects inserts into Elasticsearch. ES success is intentionally outside the ingestion acknowledgement path.

### Meaning of `202 Accepted`

`202 Accepted` means the event was validated and successfully accepted into the process-local queue abstraction. Because the assignment requires an in-process simulated queue, this acknowledgement is **not durable across application-process failure**. A crash after 202 but before Mongo persistence can lose the queued event.

With real SQS, the durability boundary moves to a successful SQS `SendMessage` response and API/worker processes can scale independently.

## 4. Queue guarantees

The local queue models these SQS concepts:

- bounded queue capacity;
- message IDs and immutable bodies;
- long polling / wait timeout;
- receipt handles scoped to each delivery attempt;
- visibility timeout;
- explicit delete on success;
- redelivery after visibility expiry;
- `ApproximateReceiveCount`-like attempt tracking;
- visibility changes for retry backoff;
- redrive to a simulated DLQ after max receives.

It does **not** provide:

- process-crash durability;
- cross-host replication;
- multi-process consumers;
- true distributed visibility coordination;
- SQS Standard's service-level durability/availability guarantees.

The local queue therefore demonstrates processing semantics, not infrastructure durability.

## 5. MongoDB model and ownership

MongoDB owns the canonical event document. The minimum persisted shape is:

```json
{
  "_id": "ObjectId",
  "event_id": "opaque immutable string/UUID",
  "event_type": "pageview",
  "timestamp": "UTC datetime supplied by event producer",
  "ingested_at": "UTC server datetime",
  "user_id": "user-123",
  "source_url": "https://example.test/path",
  "metadata": {},
  "payload_hash": "sha256:...",
  "idempotency_key_hash": "optional sha256:...",
  "schema_version": 1
}
```

The platform stores both producer event time (`timestamp`) and server acceptance/persistence time (`ingested_at`). They answer different questions and must not be conflated.

MongoDB also stores small operational collections such as search projection checkpoints,
projector leases, rebuild metadata/leases, and scoped idempotency records. These are
operational control records; the events collection remains the business source of truth.

Storage schema ownership is explicit. The `event_platform.cli storage bootstrap`
command is the release-time mutation actor: it creates the additive versioned
manifest and records an immutable schema-state fingerprint. Application replicas
run verification semantics during lifespan startup before creating workers or
projectors, and fail startup on missing, incompatible, or drifted state. The
Compose `storage-bootstrap` one-shot service runs this actor after Mongo replica
set initialization. No application startup path silently creates or rewrites a
shared schema.

## 6. MongoDB indexes

Required baseline indexes:

1. unique `{event_id: 1}` — idempotent persistence/replay safety;
2. `{timestamp: -1, event_id: -1}` — default chronological cursor pagination/date ranges;
3. `{event_type: 1, timestamp: -1, event_id: -1}` — event-type + time queries;
4. `{user_id: 1, timestamp: -1, event_id: -1}` — user + time queries;
5. `{source_url: 1, timestamp: -1, event_id: -1}` — exact source URL + time queries;
6. unique `projector` on `search_projection_checkpoints`;
7. unique `rebuild_id` and descending `started_at` on `search_rebuilds`; and
8. the built-in `_id_` access path for the fixed `search_rebuild_leases`,
   `search_projection_leases`, and `storage_schema` records; and
9. a bounded TTL index on `event_idempotency.created_at` so abandoned coordination
   records cannot grow without bound.

Do **not** index arbitrary metadata in MongoDB. Do **not** create every permutation of filter fields. Each additional index increases write amplification, memory/disk usage, and operational cost. When multiple optional filters are supplied, MongoDB can use the most selective supported index and apply residual predicates.

The required index set is defined once in `src/event_platform/storage/mongo.py`
for events and extended by the versioned manifest in
`src/event_platform/storage/bootstrap.py`. New compound indexes require measured
query-plan evidence and an explicit schema version decision.

For very large-scale analytics, pre-aggregated/materialized time buckets become preferable; that is an evolution, not required in this assessment.

## 7. Canonical query API

`GET /events` reads MongoDB and supports:

- `event_type`
- `start`
- `end`
- `user_id`
- `source_url`
- bounded `limit`
- opaque cursor

Results are sorted by `(timestamp DESC, event_id DESC)` and use keyset pagination. No unbounded offset/skip pagination.

## 8. Analytics

`GET /events/stats` uses a Mongo aggregation pipeline with `$match`, `$dateTrunc`, `$group`, and `$sort` to return counts by event type and a configurable UTC time bucket: hour, day, or week.

Date ranges are bounded to protect the service. The response records effective range and bucket so results are self-describing.

## 9. Elasticsearch projection

### Why ES is not written in the ingestion transaction

Coupling Mongo and Elasticsearch writes in the persistence worker would make search availability part of event durability and create unavoidable partial-success states. Instead, Mongo emits an insert Change Stream after canonical persistence. A search projector consumes it and indexes the derived document.

Consequences:

- search is eventually consistent;
- ES outage does not cause canonical event loss;
- ES can be rebuilt from Mongo;
- projection lag is measurable and must be exposed.

Feature 010 implements this boundary in `src/event_platform/search/projection.py`, with the official async Elasticsearch adapter in `search/elasticsearch.py`, Mongo checkpoint persistence in `storage/checkpoints.py`, and an insert-only async source in `storage/change_stream.py`. The coordinator writes the stable alias and optional rebuild target before saving the resume token. It reports bounded state and lag values, retains the checkpoint across transient failures, and enters `reconciliation_required` for invalid resume history. Resume tokens and raw dependency details are never exposed in status or logs.

Lifecycle delivery safety is explicit: shutdown stops queue admission first, leaves the
drainable persistence worker running while accepted queue depth and in-flight work drain,
then signals/cancels tasks at the grace deadline. It reports residual depth when the
deadline is exceeded. Workers renew active visibility during slow canonical persistence,
and stale receipt operations become bounded ownership-loss outcomes. The supervisor
leaves shared resources isolated when a cancellation-resistant task remains attached.

On first deployment, the application creates the mapped `events-v000001`
generation and attaches the configured stable alias when no generation exists.
This bootstrap only initializes derived search state; Mongo remains canonical
and later generation replacement remains owned by the online rebuild flow.

### Projection checkpointing

The projector persists a Change Stream resume token/checkpoint **after** the corresponding ES write has succeeded. If the process crashes after ES indexing but before checkpoint persistence, the change may replay; indexing by immutable `event_id` makes that replay safe.

If a resume token becomes invalid (for example after oplog history is no longer available), the system logs the condition and requires/initiates a full rebuild/reconciliation path rather than silently skipping data.

Projector replicas acquire the Mongo-backed `search_projection_leases` lease before
consuming. The lease carries an owner and monotonically increasing fencing generation;
renewal and checkpoint writes are owner/generation constrained, so a stale replica
cannot regress shared progress after takeover. Search writes use bounded Elasticsearch
bulk operations where the adapter supports them, and checkpoints advance through the
acknowledged batch in source order. Partial bulk failures retry idempotently by event ID.

Projector replicas acquire the Mongo-backed `search_projection_leases` lease before
consuming. The lease carries an owner and monotonically increasing fencing generation;
renewal and checkpoint writes are owner/generation constrained, so a stale replica
cannot regress shared progress after takeover. Search writes use bounded Elasticsearch
bulk operations where the adapter supports them, and checkpoints advance through the
acknowledged batch in source order. Partial bulk failures retry idempotently by event ID.

## 10. Elasticsearch mapping

The index has `dynamic: false` at the top level. Stable fields have explicit mappings:

- `event_id`: `keyword`
- `event_type`: `keyword`
- `timestamp`: `date`
- `ingested_at`: `date`
- `user_id`: `keyword`
- `source_url`: `keyword`
- `metadata`: `flattened`
- `metadata_text`: `text` with a conservative analyzer (`standard` tokenizer + lowercase + asciifolding)

`metadata_text` is a deterministic projection of metadata scalar keys/values suitable for full-text search. `flattened` retains the flexible object without exploding the mapping into unbounded dynamic fields.

No language-specific stemming is used because event metadata commonly contains product names, identifiers, browser/device names, and short technical strings where aggressive stemming can reduce precision.

Feature 011 owns the fixed mapping and read-side search boundary in `src/event_platform/search/mapping.py`, `search/search.py`, and `api/routes/search.py`. `GET /events/search` accepts only bounded typed terms and exact filters, builds a fixed query, and returns signed filter-bound continuation cursors ordered by timestamp and event ID. It never accepts client Elasticsearch DSL and maps dependency or decode failures to safe 503 responses.

## 11. Online Elasticsearch rebuild

All callers and the live projector write/search through a stable alias, e.g. `events-search`. Physical generations are immutable names such as `events-v000001`, `events-v000002`.

Rebuild algorithm:

1. acquire a Mongo-backed rebuild lease so only one rebuild runs;
2. create a new physical generation with the exact desired settings/mapping;
3. create a `rebuild_id` record and mark the target generation as actively rebuilding;
4. live change-stream projector continues indexing through the alias **and also dual-writes each new event to the active rebuild target**;
5. capture the maximum Mongo generated `_id` as the durable canonical high-water boundary;
6. bulk scan canonical Mongo events with `_id <= high-water` and idempotently index them into the target;
7. record bulk failures and retry only retryable ES errors;
7. wait for the change-stream projector source-position checkpoint to reach a fresh canonical high-water boundary, then reconcile every canonical event identity through that boundary against the candidate;
8. atomically swap `events-search` alias from old generation to target generation in one aliases update request;
9. mark rebuild complete and stop the extra dual write; a post-swap state failure records `reconciliation_required` and never deletes the serving candidate;
10. retain the previous generation for a configurable rollback window before cleanup.

Because live inserts are dual-written while the bounded Mongo snapshot is built, callers keep using the old alias until the new generation is caught up, then the alias switches atomically. Rebuilds are seamless to API callers but highly visible operationally. The rebuild lease fencing token is included in state writes, so stale owners cannot advance or regress a newer run. Candidate verification rejects a missing or wrong event ID even when a document count happens to match.

Feature 012 implements the rebuild coordinator in `src/event_platform/search/rebuild.py`, the executable dependency graph in `search/rebuild_runtime.py`, Mongo high-water source and lease/state persistence in `storage/rebuild_source.py` and `storage/rebuilds.py`, Elasticsearch generation/alias operations in `search/elasticsearch_rebuild.py`, and read-only status in `api/routes/rebuild.py`. The coordinator activates the Feature 010 target callback before capturing the boundary, retries transient bulk failures, waits for projector convergence, performs bounded identity verification, performs one atomic alias action, and retains rollback metadata without logging document bodies.

Structured rebuild events include:

- `search_rebuild.started`
- `search_rebuild.index_created`
- `search_rebuild.bulk_progress`
- `search_rebuild.reconciliation_started`
- `search_rebuild.verification_completed`
- `search_rebuild.alias_swapped`
- `search_rebuild.completed`
- `search_rebuild.failed`

Include `rebuild_id`, source collection, old/new index, counts, failures, phase, and duration.

## 12. Redis realtime cache

`GET /events/stats/realtime` uses cache-aside:

```text
request
  ├─ Redis hit  ──► deserialize and return
  └─ Redis miss ──► aggregate Mongo ──► SET with TTL ──► return
```

The default TTL should be short (target: 10 seconds, configurable). A realtime dashboard tolerates small staleness, and short expiration avoids explicit invalidation on every write. Include `generated_at`, window bounds, and `X-Cache: HIT|MISS|BYPASS` to make behavior visible.

If Redis is unavailable, compute from Mongo and return with `X-Cache: BYPASS`; do not fail the endpoint solely because the cache is unavailable.

Feature 013 implements this boundary in `src/event_platform/cache/realtime.py` and
`src/event_platform/api/routes/realtime_stats.py`. The key is versioned by schema,
window length, and the bounded event-type cardinality,
payloads are validated deterministic JSON without raw event metadata, the default
window is five minutes (bounded to 1..60), the default TTL is ten seconds, and a
bounded process-local single-flight lock coalesces same-key misses. Mongo remains
the canonical aggregation source; Redis read/write/decode errors emit a structured
degraded cache event and return the Mongo result with `BYPASS`.

At much higher write/read volume, evolve toward incremental counters or materialized rolling windows rather than repeatedly re-running the same Mongo aggregation.

## 13. Mandatory rate limiting

Externally exposed application routes use bounded admission control. The primary limiter is a Redis-backed atomic leaky bucket (Lua script or equivalent atomic operation). Keying is by the stable authenticated token-derived client scope in production, or normalized direct-peer identity in local mode, plus route class. Accepted requests reserve a release slot and wait asynchronously, smoothing bursts without dropping them.

Redis failure does not disable protection. The application switches to a conservative process-local leaky bucket and emits degraded health/log/metric state.

Return `429 Too Many Requests` with `Retry-After` and useful rate-limit headers only when
the bounded reservation backlog or the process-wide delayed-request gate is full. Health
probes are exempt or separately protected to avoid defeating orchestration.

The implementation lives in `src/event_platform/rate_limit/` with atomic Redis
Lua leaky-bucket reservations, bounded monotonic local fallback, direct-peer identity by
default, and route-class middleware at
`src/event_platform/api/middleware/rate_limit.py`. Redis failures emit a
structured degraded event and continue with the conservative local policy.

The service must not trust `X-Forwarded-For` unless configured trusted proxy hops make that header authoritative.

### Lifecycle ownership and shutdown

Feature 016 uses `src/event_platform/core/lifecycle.py` as the single owner of
background tasks and dependency close callbacks. Startup creates only configured
Mongo, Elasticsearch, and Redis clients; the persistence worker is started when
the Mongo store is available. Shutdown first stops queue admission, keeps the
drainable persistence worker running until accepted work is empty or the bounded
grace period expires, then signals managed workers/projectors and cancels any
remaining tasks, records residual in-memory queue depth, and then closes queue, Redis,
Elasticsearch, and Mongo in that order. Critical task failures move the supervisor to
`failed`; a degradable projector failure records component degradation without closing
canonical admission or readiness. The in-memory queue can still lose visible messages
on process crash; the accepted-202 contract and depth log make that limitation explicit.

## 14. Failure modes

### MongoDB unavailable

- New events can continue entering the bounded local queue briefly.
- Worker classifies connection/timeouts as transient and retries with backoff.
- Queue depth/retry metrics rise.
- Once queue capacity is exhausted, `POST /events` returns 503 rather than accepting work it cannot hold.
- Canonical query/analytics endpoints return a dependency-unavailable problem response.
- Readiness becomes unhealthy because the core durability dependency is unavailable.

### Worker crashes mid-processing

- If it crashes before Mongo insert, visibility expiration redelivers the message.
- If it crashes after Mongo insert but before queue delete, redelivery attempts the same `event_id`; unique index/idempotency logic verifies equivalence and then acknowledges.
- Whole-process crash can lose still-queued in-memory messages. This is explicitly a simulation limitation addressed by real SQS.

### Elasticsearch unavailable

- Mongo persistence and Mongo query/analytics continue.
- Change-stream projector stops advancing checkpoint until writes succeed or enters controlled backoff.
- Search endpoint returns a clear 503 dependency problem instead of silently falling back to semantically different Mongo full-text behavior.
- Projection lag and failure metrics/logs surface the degradation.
- On recovery the projector resumes; rebuild remains available if checkpoint history is invalid.

### Redis unavailable

- realtime stats compute from Mongo and bypass cache;
- rate limiter uses conservative local fallback;
- ingestion and canonical queries continue;
- component health is degraded, not necessarily globally unready.

### Elasticsearch rebuild fails

- stable alias remains pointed at the last verified index;
- target generation is marked failed and never swapped into service;
- live search remains available on the old generation if ES itself is healthy;
- failure is logged with `rebuild_id` and retained for inspection.

## 15. Scaling to 10x

Likely pressure points, in order:

1. **Process-local queue / single API process.** Replace with real SQS; run stateless API fleet and independent worker fleet. Long polling, visibility timeout, redrive policy, and DLQ become provider-managed.
2. **Mongo write throughput/index cost.** Tune bulk worker writes, connection pools, index set, and storage tier; shard by a deliberate key only when measurements justify it.
3. **Change-stream projector throughput.** Partition/scale projection consumers carefully, or introduce a durable projection stream/outbox if ordering/throughput needs exceed one consumer.
4. **Analytics scans.** Add pre-aggregated time-bucket collections or stream-materialized rollups.
5. **Elasticsearch shards/index lifecycle.** Size shards from measured document volume, use rollover/data streams only if the access/retention model benefits.
6. **Realtime cache stampedes/hot keys.** Use incremental counters, request coalescing, or partitioned aggregates.
7. **Rate limiting.** Redis-backed leaky-bucket reservations already coordinate multiple API instances; consider API-key/tenant identity rather than IP once authentication exists.

## 16. Production SQS drop-in

The code must hide queue implementation behind a small port/protocol. Replacing `InMemorySqsQueue` with SQS changes:

- enqueue durability becomes SQS `SendMessage` success;
- API and workers become separate deployable/scalable processes;
- receipt handles/visibility/delete map to native APIs;
- retry redrive moves to queue redrive policy/DLQ;
- long polling becomes SQS `ReceiveMessage(WaitTimeSeconds=...)`;
- IAM replaces local queue access;
- CloudWatch/queue metrics supplement application metrics;
- payload size limits and possible object-store indirection must be considered;
- Standard queues remain at-least-once and best-effort ordered; idempotent worker behavior remains required.

Do not redesign business logic when swapping queue implementations.

## 17. Demo/reviewer UI

The UI is intentionally operational and compact. It demonstrates backend capabilities:

- dashboard/service health;
- event generator and burst generation;
- event list/filter/pagination;
- metadata full-text search;
- hourly/daily/weekly analytics;
- realtime cache status;
- queue/retry/DLQ counts;
- search projection lag/rebuild status.

The API remains fully usable without the UI.

## 18. Postman

Postman is a first-class reviewer surface. The collection must contain assertions and an ordered demo workflow, including polling for asynchronous persistence/search visibility rather than fixed sleeps.

## 19. Deployment topology for the assessment

Docker Compose services:

- `app` — FastAPI + local queue + persistence worker + change-stream search projector;
- `mongo` — single-node replica set;
- `mongo-init` — one-shot replica-set initialization if needed;
- `elasticsearch` — single node for local demo;
- `redis` — cache/rate limiting;
- `ui` — static reviewer console behind nginx/reverse proxy.

The app service runs one process. Production notes explain how SQS removes this restriction.

## 20. Deliberate non-goals

- frontend product development beyond the reviewer console;
- exactly-once claims;
- Mongo full-text search as a fallback for ES;
- arbitrary metadata indexes in Mongo or dynamic ES mappings;
- microservices solely for separation aesthetics;
- Kubernetes/cloud IaC in the take-home;
- authentication/user management not requested by the assessment.
