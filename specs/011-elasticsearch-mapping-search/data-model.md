# Feature 011 Data Model

## SearchDocument

Canonical event fields plus `metadata` (flattened object) and `metadata_text` (analyzed deterministic text).

## SearchQuery

Bounded `q`, optional exact `event_type`/`user_id`, optional UTC inclusive `start`/`end`, page size 1-200, and opaque signed cursor.

## SearchPage

`items`, `limit`, `next_cursor`, and request ID.
