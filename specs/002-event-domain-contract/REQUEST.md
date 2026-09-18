# Feature Request: Event Domain Contract

## Intent

Define the event contract precisely before ingestion/storage code exists.

## Required input fields

- `event_type`: non-empty string, bounded length; examples pageview/click/conversion but not an enum that blocks new event types.
- `timestamp`: timezone-aware ISO 8601 datetime; normalize to UTC; reject naive timestamps.
- `user_id`: non-empty bounded string.
- `source_url`: valid HTTP/HTTPS URL, bounded total length; persist normalized string without destructive semantic rewriting.
- `metadata`: flexible JSON object subject to explicit max serialized size, max nesting depth, max key count, key length, and sensible scalar/list constraints.

## Server fields

`event_id`, `ingested_at`, `schema_version`, `payload_hash`, optional hashed idempotency key.

## Decisions that must be explicit in spec

- permitted producer timestamp skew into the future;
- whether very old historical events are accepted;
- JSON number/string/list/null handling in metadata;
- deterministic canonicalization used for payload hashing;
- error response for metadata too large/deep.

## Security

Validation must defend against huge/deep JSON, absurd strings, non-HTTP URLs, and log injection. Do not log full arbitrary metadata on validation failure.

## Tests

Boundary lengths, timezone normalization, invalid URL schemes, nesting/size limits, stable payload hash, Unicode behavior.


## Dependencies

001

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
