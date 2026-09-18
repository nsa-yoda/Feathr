# System Context

## Actors

- **Event producers:** web/backend clients sending individual events.
- **Reviewers/operators:** engineers evaluating behavior through API, Postman, logs, metrics, and demo UI.
- **Application:** FastAPI process containing HTTP handlers and assessment-mandated in-process workers.
- **MongoDB:** canonical event persistence and control/checkpoint records.
- **Elasticsearch:** derived search index.
- **Redis:** realtime cache and distributed rate-limit state.

## Trust boundaries

HTTP input is untrusted. Event metadata is arbitrary JSON within strict size/depth/type limits. Mongo/ES/Redis are private Compose-network dependencies. Ops/status endpoints are reviewer-oriented and must not expose secrets or complete arbitrary metadata.

## Runtime constraint

The assessment's in-process queue means there is one application process. Running Uvicorn/Gunicorn with multiple workers would create multiple unrelated queues. Production SQS removes the runtime coupling and allows independent scaling.
