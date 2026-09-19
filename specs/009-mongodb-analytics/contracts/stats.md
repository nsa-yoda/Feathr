# Event Statistics Contract

## `GET /events/stats`

Query parameters:

- `bucket`: `hour`, `day`, or `week`; default `hour`.
- `start`, `end`: optional UTC-aware ISO timestamps. Both omitted selects the previous 24 hours; only one is invalid.

Successful `200 application/json` response:

```json
{
  "bucket": "hour",
  "timezone": "UTC",
  "start": "2026-01-01T00:00:00Z",
  "end": "2026-01-02T00:00:00Z",
  "points": [
    {"bucket": "2026-01-01T00:00:00Z", "event_type": "pageview", "count": 4}
  ],
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

Points are ordered by bucket ascending and event type ascending. The result is bounded to 10,000 points; a valid range that exceeds the bound returns a safe 422 rather than partial counts. The canonical aggregation also has a finite 5-second Mongo `maxTimeMS` deadline; timeout or dependency failure uses the shared 503 contract. Empty ranges return `points: []`. Invalid input uses the shared 422 problem contract; missing or unavailable canonical storage uses the shared 503 contract with `Retry-After: 1`.
