# Feature 005 Data Model

`IngestResponse` contains `event_id: UUID`, `status: "queued"`, and `request_id: UUID`. The queue body is the Feature 002 canonical event JSON envelope and contains `idempotency_key_hash`, never the raw header.
