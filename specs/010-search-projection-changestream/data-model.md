# Feature 010 Data Model

## ProjectionCheckpoint

- `projector`: stable bounded name (`events-search`)
- `resume_token`: BSON-safe opaque value, never returned or logged
- `state`: `starting | running | retrying | degraded | reconciliation_required | stopped`
- `updated_at`: UTC timestamp
- `last_projected_event_at`: UTC timestamp or absent
- `failure_code`: bounded safe code or absent

## ProjectedEvent

- `event_id`: immutable UUID string and Elasticsearch `_id`
- `event_type`, `timestamp`, `user_id`, `source_url`, `metadata`: canonical fields
- `schema_version`: canonical version

## ProjectionStatus

- `state`, `checkpoint_present`, `last_success_at`, `last_projected_event_at`, `lag_seconds`, `failure_code`
- Resume token and raw dependency details are excluded.
