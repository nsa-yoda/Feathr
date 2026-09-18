# Ingestion API Contract

`POST /events` accepts the five producer fields plus optional `Idempotency-Key`, returns `202 application/json` after successful queue handoff, and returns `application/problem+json` for validation or queue-capacity failures.
