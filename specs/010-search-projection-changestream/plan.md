# Feature 010 Implementation Plan: Mongo Change-Stream Search Projection

## Summary

Add a typed async search projection package. It owns deterministic event projection, an Elasticsearch port, Mongo change-stream/checkpoint ports, retry state, and an optional rebuild-target writer. Application lifecycle wiring remains explicit and can be adopted by the later runtime/lifecycle feature.

## Technical Context

- Python 3.12+, FastAPI repository, Pydantic v2, PyMongo Async, official Elasticsearch async client.
- Mongo is canonical; Elasticsearch is derived and eventually consistent.
- Existing `CanonicalEvent` and `MongoEventStore` are the domain/storage boundaries.
- New modules: `src/event_platform/search/projection.py`, `src/event_platform/search/elasticsearch.py`, `src/event_platform/storage/checkpoints.py`, and `src/event_platform/storage/change_stream.py`.

## Design

1. `project_event` maps canonical fields to a stable document source and uses `event_id` as ID.
2. `ElasticsearchProjectionWriter` writes alias first and optional target second, requiring acknowledgement from all writes.
3. `ProjectionCheckpointStore` loads/saves one BSON-safe checkpoint document by projector name.
4. `MongoChangeStreamSource` opens an async insert-only stream with `resume_after` when a checkpoint exists.
5. `SearchProjector` coordinates startup, change handling, bounded retry classification, status, and shutdown. Resume history errors transition to reconciliation-required.
6. Logging uses existing structured logging conventions and emits operation-safe state transitions without token or body data.

## Test Strategy

- Unit tests use fake ES, checkpoint, and stream ports for ordering, replay, failures, state, and retry behavior.
- Integration tests use real MongoDB replica set and Elasticsearch when `MONGO_URI` and `ELASTICSEARCH_URL` are configured; otherwise they skip with an explicit environment reason.
- Failure tests verify invalid token, ES outage, malformed change, and cancellation semantics.

## Risks and Mitigations

- ES API drift: isolate the official client in `elasticsearch.py` and test acknowledgement/error translation.
- Resume history loss: never fall back to `now`; make reconciliation state terminal and observable.
- Replay after ES success before checkpoint save: stable event ID makes the second index operation harmless.
- Checkpoint token shape: validate BSON-safe values at the repository boundary and never expose the value in status/logs.
