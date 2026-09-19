# Feature 013 Realtime Stats Contract

## `GET /events/stats/realtime`

Query:

- `window_minutes`: optional integer from 1 through 60; default 5.

Success `200` response:

```json
{
  "schema_version": 1,
  "total_events": 12,
  "by_event_type": {"pageview": 10, "purchase": 2},
  "generated_at": "2026-01-01T12:00:03Z",
  "window_start": "2026-01-01T11:55:03Z",
  "window_end": "2026-01-01T12:00:03Z",
  "request_id": "00000000-0000-0000-0000-000000000001"
}
```

Headers:

- `X-Cache: HIT|MISS|BYPASS`
- `X-Request-ID`: generated request identifier.

Errors use the existing `application/problem+json` contract. Invalid window values return 422;
Mongo failure returns 503 with `Retry-After: 1`. Redis failure does not change a successful 200;
it changes `X-Cache` to `BYPASS` and is logged as degraded.
