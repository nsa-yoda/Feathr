# Feature 003 Data Model

## Repository values

- `EventQuery`: typed filters plus `limit` (1–1000), optional inclusive `timestamp_from`/`timestamp_to`, and optional exclusive `after_timestamp`/`after_event_id` pair. Query string lengths and date ranges are bounded at this repository boundary; opaque cursor encoding and public API defaults belong to Feature 008.
- `CanonicalEvent`: Feature 002 model serialized to a BSON-safe mapping.
- `IndexDefinition`: deterministic name and ordered `(field, direction)` pairs.

## Required indexes

| Name | Keys | Options |
|---|---|---|
| `uq_events_event_id` | `event_id ASC` | unique |
| `ix_events_timestamp_event_id` | `timestamp DESC, event_id DESC` | — |
| `ix_events_event_type_timestamp_event_id` | `event_type ASC, timestamp DESC, event_id DESC` | — |
| `ix_events_user_id_timestamp_event_id` | `user_id ASC, timestamp DESC, event_id DESC` | — |
| `ix_events_source_url_timestamp_event_id` | `source_url ASC, timestamp DESC, event_id DESC` | — |
