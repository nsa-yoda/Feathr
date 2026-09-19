# Feature 011 Search Contract

`GET /events/search?q=<term>&event_type=<type>&user_id=<id>&start=<UTC>&end=<UTC>&limit=50&cursor=<opaque>`

- 200 returns `items`, `limit`, `next_cursor`, and `request_id`.
- 422 returns `application/problem+json` for invalid bounds, dates, or cursor.
- 503 returns `application/problem+json` with `Retry-After: 1` when Elasticsearch is unavailable or returns an invalid response.
- Clients cannot provide Elasticsearch JSON DSL, scripts, fields, or sort expressions.
