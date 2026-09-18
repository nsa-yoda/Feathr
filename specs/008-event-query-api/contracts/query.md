# Event Query API Contract

## `GET /events`

Query parameters:

- `event_type`, `user_id`: bounded exact strings
- `start`, `end`: optional UTC-aware timestamps, inclusive
- `source_url`: optional exact normalized HTTP URL
- `limit`: integer 1–200, default 50
- `cursor`: optional bounded signed versioned continuation token

Successful response is `200 application/json`:

```json
{
  "items": [],
  "limit": 50,
  "next_cursor": null,
  "request_id": "00000000-0000-0000-0000-000000000000"
}
```

Invalid parameters use the shared `application/problem+json` contract with 422. Missing/unavailable canonical storage uses the same contract with 503. The route does not return Mongo `_id` or raw driver details.
