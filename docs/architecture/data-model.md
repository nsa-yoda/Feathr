# Data Model and Envelope Details

## HTTP event input

The client controls `event_type`, `timestamp`, `user_id`, `source_url`, and `metadata` only. Internal operational fields are server-owned and client attempts to inject them should be rejected or ignored consistently according to the Pydantic model policy.

## Canonical event

Persist an immutable event record with server-generated identity and ingestion time. `payload_hash` must be computed from a deterministic canonical representation of the client-controlled semantic payload, not Mongo `_id`, request ID, or arrival time.

`event_id` should be safe for use as Mongo unique key, API identifier, and Elasticsearch `_id`. The implementation may use UUID/ULID-like identifiers, but ordering must never depend on random UUID lexical properties unless the pagination design explicitly guarantees it. Since primary list sort includes producer timestamp, use `event_id` only as a stable tie-breaker.

## Queue envelope

The queue body should contain the validated event-to-persist plus processing context such as event ID, payload hash, safe request ID, and enqueue timestamp. Retry state that belongs to queue delivery should remain queue metadata rather than mutating the event body.

## Projection checkpoint

Persist one search projector checkpoint record with projection name/version, resume token in a BSON-safe representation, updated time, and last successfully projected event diagnostics. Never advance before required ES writes complete.

## Search rebuild record

Track rebuild ID, state/phase, lease owner and expiry, source collection, active alias/old index/target index, processed/indexed/failed counts, timestamps, and sanitized failure summary. This provides an audit trail independent of logs.
