# Feature Request: Async Ingestion API

## Endpoint

`POST /events`

## Success contract

Validate request fully, construct event envelope, enqueue it, then return `202 Accepted`. Response contains immutable event ID, `queued` status, request ID, and optional status wording that makes clear processing is asynchronous.

## Ownership boundary

Before successful enqueue the HTTP handler owns the request. After successful enqueue, the local queue owns processing responsibility **within the life of the process**. The API must not write the event synchronously to MongoDB.

## Backpressure

If queue capacity cannot accept within the configured enqueue timeout, return `503` + `Retry-After`. Do not block an HTTP worker indefinitely and do not return 202 for dropped work.

## Idempotency header

Accept optional `Idempotency-Key` with strict length/character bounds. The precise durable/best-effort semantics are completed in Feature 006; the route must carry it through without logging the raw secret-like value.

## Rate limiting

Feature 014 applies middleware/policy globally; ingestion tests should eventually assert 429 semantics without conflating rate limit with queue saturation.

## Tests

202 after enqueue, validation errors, queue-full 503, request ID propagation, OpenAPI schema.


## Dependencies

002, 004

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
