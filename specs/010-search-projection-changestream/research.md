# Feature 010 Research

1. Use PyMongo's async change-stream API at the canonical Mongo boundary; do not read a second event source.
2. Use the official async Elasticsearch client and keep it behind a small projector-owned port so unit tests can use deterministic fakes while integration tests use real services.
3. Persist checkpoints in Mongo after required ES writes. Mongo remains authoritative for accepted events; a checkpoint is operational state, never an event source.
4. Store resume tokens as BSON-safe values without logging them. Invalid token/history errors map to `reconciliation_required` rather than silent skip.
5. Use the immutable event ID as Elasticsearch `_id`; at-least-once replay is therefore idempotent.
6. Keep retry delay injectable and bounded. The worker must release execution while waiting and must not advance a checkpoint on any failed required write.
7. Leave stable alias generation and online rebuild orchestration to Feature 012, but define a target-writer seam for dual writes.
