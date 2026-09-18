# Feature Request: Observability and Health

## Logs

Structured JSON runtime logging with request IDs and operation IDs. Normalize event names. Avoid full payload/metadata logging.

## Request correlation

Accept a safe bounded incoming request ID only if valid; otherwise generate one. Return it in response headers and problem documents. Propagate it into enqueue envelope/background logs when available.

## Metrics

Prometheus endpoint with low-cardinality labels. Cover HTTP, queue, workers, Mongo, ES projection/rebuild, Redis cache, rate limiting, and lifecycle state.

## Health

- `/health/live`: cheap process liveness;
- `/health/ready`: core ability to accept/process durable events — Mongo and essential local workers must be viable;
- `/health/components`: Mongo, ES, Redis, queue, persistence worker, search projector with healthy/degraded/unhealthy state and safe details.

ES or Redis degradation should not automatically make global readiness false if canonical ingestion can proceed. Mongo failure should.

## Tests

Health state transitions with dependency fakes/integration where sensible, request IDs, metrics increment, no high-cardinality labels.


## Dependencies

001, 003, 004, 010, 013, 014

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
