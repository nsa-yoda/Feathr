# Feature 013 Data Model

## RealtimeStatsQuery

- `window_minutes`: integer 1..60, default 5.
- `window_start`: UTC `window_end - window_minutes`.
- `window_end`: injected/server UTC timestamp with second precision.
- `max_event_types`: bounded cardinality setting included in cache identity.

## RealtimeStatsResponse

- `schema_version`: fixed cache schema identifier.
- `total_events`: non-negative bounded integer.
- `by_event_type`: deterministic map of bounded event-type strings to positive counts.
- `generated_at`: UTC timestamp when Mongo computation completed.
- `window_start`, `window_end`: inclusive UTC bounds.
- `request_id`: request correlation UUID.

## CacheEntry

The serialized response is stored with a versioned key containing window and cardinality
parameters and a short TTL. It contains no raw event metadata or dependency credentials.
Invalid payloads, non-UTC timestamps, negative grouped counts, and total/count mismatches are discarded as misses.
