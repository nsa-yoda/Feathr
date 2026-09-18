# Observability Contract

## Logs

JSON logs include `timestamp`, `level`, `service`, `event`, `request_id` when applicable, operation identifiers, and safe structured fields. The foundation service uses `service: "event_platform"`. Never log full arbitrary metadata by default.

Required event families include HTTP completion/errors, queue enqueue/receive/delete/redelivery/DLQ, worker processing, Mongo dependency state, ES projection/checkpoint/rebuild, Redis cache hit/miss/bypass, rate-limit allow/deny/fallback, and lifecycle startup/shutdown.

## Metrics

At minimum:

- HTTP request count/duration/status by route template;
- ingestion accepted/rejected;
- queue visible/inflight/DLQ depth and oldest age;
- worker processed/retried/DLQ and duration;
- Mongo operation latency/errors;
- ES projected/errors/lag/rebuild phase;
- cache hit/miss/bypass and computation latency;
- rate-limit allowed/denied/fallback;
- process worker/background-task health.

Avoid unbounded-cardinality labels such as user ID, URL, request ID, or event ID.

## Health

- liveness: process/event loop is alive;
- readiness: core ingestion durability path can make progress (Mongo + worker + queue operational);
- component health: separate Mongo, ES, Redis, projector, queue state with healthy/degraded/unhealthy detail.
