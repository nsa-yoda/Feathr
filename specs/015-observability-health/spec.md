# Feature Specification: Observability and Health

**Feature Branch**: `015-observability-health`  
**Status**: Accepted  
**Input**: `REQUEST.md`

## User scenarios

### Structured operations

Operators can consume one JSON object per runtime event. HTTP requests, queue and
worker work, dependency outcomes, rate-limit decisions, and lifecycle transitions
use stable event names and bounded fields. Request and operation IDs correlate a
single action without logging bodies, credentials, raw URLs, or exception text.

### Safe request correlation

The service accepts a bounded canonical UUID from `X-Request-ID`; malformed,
oversized, or missing values are replaced with a server UUID. The response and
problem document return that ID. Every request also receives a server operation
UUID for logs and background handoff correlation.

### Health and metrics

`/health/live` stays a cheap process check. `/health/ready` requires Mongo,
queue, and persistence-worker viability. `/health/components` reports fixed
component names with `healthy`, `degraded`, or `unhealthy` and safe details.
Elasticsearch and Redis degradation does not make readiness false when durable
ingestion remains viable. `/metrics` returns Prometheus text with fixed,
low-cardinality labels and no request IDs, event IDs, or raw paths.

## Requirements

- **FR-001**: Runtime logs MUST be JSON with stable event names, request/operation correlation when available, and safe bounded fields.
- **FR-002**: Request IDs MUST accept only canonical UUID values no longer than 128 bytes and MUST be generated otherwise.
- **FR-003**: Responses and problem documents MUST include the effective request ID; responses MUST include an operation ID header.
- **FR-004**: Metrics MUST expose HTTP, queue, worker, Mongo, Elasticsearch, Redis, rate-limit, and lifecycle families with bounded labels.
- **FR-005**: Liveness MUST avoid dependency network calls.
- **FR-006**: Readiness MUST fail with 503 when Mongo or essential local processing is unhealthy, while derived ES/Redis degradation remains visible but non-blocking.
- **FR-007**: Component health MUST expose only a fixed component vocabulary and safe status details.
- **FR-008**: Tests MUST cover valid/invalid correlation, health transitions, metric increments, and cardinality protection.

## Acceptance scenarios

1. A valid UUID request ID is echoed; malformed and oversized values are replaced.
2. A request completion emits a structured event and increments a fixed route/status metric.
3. Mongo failure returns readiness 503; ES/Redis degraded with healthy core returns readiness 200.
4. Component and metrics responses contain no raw exception, URL identifier, event ID, or request ID.
