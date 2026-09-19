# Feature 019 Quickstart

## Service inputs

Set `MONGO_URI`, `ELASTICSEARCH_URL`, and/or `REDIS_URL` for the scenarios under test. MongoDB must support replica-set change streams for projection scenarios.

## Run

```bash
make test-integration
```

The command runs `tests/integration -m integration --pass-with-no-tests`. Missing or unavailable services produce explicit skips; they are not evidence that the corresponding lifecycle passed. With all services reachable, run the Feature 019 module directly and repeat it with fresh namespaces to verify cleanup.

Feature 019 proves six real-service lifecycles: HTTP ingestion to canonical query, change-stream projection to search, Mongo statistics grouping, Redis cache miss/hit, duplicate redelivery, and online rebuild/search continuity. Unit, failure, browser, Compose, and Postman evidence remain separate.
