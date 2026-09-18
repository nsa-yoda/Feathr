# Assessment Brief — Normalized Requirements

This file preserves the assignment as an engineering checklist. The original prompt remains the ultimate external requirement; this normalized version exists so Codex can trace every requested behavior.

## Required technology

- Python with FastAPI or Flask — this architecture selects FastAPI.
- MongoDB for event storage and aggregation.
- Elasticsearch for metadata full-text search and analytics/search projection responsibilities.
- Redis for caching.
- Simulated in-process event queue modeled after SQS.

## Required event ingestion

- `POST /events` accepts event type, timestamp, user ID, source URL, flexible metadata.
- HTTP request validates and enqueues instead of synchronously writing Mongo.
- background worker consumes and writes Mongo.
- failures retry with basic backoff.
- queue guarantees and real-SQS differences documented.

## Required query/analytics

- `GET /events`: filter by type, date range, user ID, source URL.
- `GET /events/stats`: Mongo aggregation grouped by event type and hour/day/week bucket.
- `GET /events/search`: Elasticsearch full-text metadata search.
- `GET /events/stats/realtime`: lightweight Redis-cached summary with configurable TTL.

## Required design documentation

- caching TTL/invalidation/high-write-volume rationale;
- Mongo index implementation and rationale;
- Elasticsearch mapping and analyzers;
- intentionally omitted indexes and why;
- standalone `ARCHITECTURE.md` with diagram, responsibilities, storage rationale, failure modes, 10x scaling, and production changes.

## Required tests

- meaningful unit tests for business/error behavior;
- at least two end-to-end integration lifecycles;
- README testing philosophy and future priorities;
- pytest preferred.

## Required engineering quality

Clear module boundaries, appropriate HTTP responses, internal logging, and team-maintainable code.

## AI workflow requirement

README must state tools used, concrete AI contributions, pushback/corrections, and how AI affected approach/speed/quality.

## Assignment bonus items adopted as mandatory for this submission

- Dockerfile and Docker Compose for all services;
- rate limiting/abuse prevention;
- event deduplication;
- simulated DLQ;
- AWS SQS drop-in design notes.

## Additional reviewer-experience requirements adopted by candidate

- Dockerized reviewer/demo UI despite frontend being unscored;
- executable Postman collection/environment with assertions and demo workflow.
