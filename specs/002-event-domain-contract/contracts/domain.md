# Event Domain Contract

## Input contract

`EventInput` accepts only `event_type`, `timestamp`, `user_id`, `source_url`, and `metadata`. Server-owned fields are rejected as extra input. Validation errors are safe categories for the later HTTP problem mapper and do not include complete metadata.

## Canonicalization contract

`CanonicalEvent.from_input` assigns an immutable UUID, UTC `ingested_at`, schema version 1, a SHA-256 payload hash, and an optional SHA-256 idempotency-key hash. The canonical payload hash is stable for equivalent producer JSON independent of object key insertion order.

## Error categories

The domain exposes ordinary typed validation errors for invalid scalar fields and explicit categories for metadata root type, size, depth, key count, key length, string length, list length, unsupported value, non-finite number, and numeric-range failures. Feature 005 maps these categories to `application/problem+json` 422 responses.
