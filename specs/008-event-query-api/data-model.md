# Data Model: Event Query API

## EventCursor

- version: integer `1`
- timestamp: normalized UTC ISO-8601 string
- event_id: UUID string
- signature: HMAC-SHA256 over the versioned payload

## EventPage

- `items`: ordered canonical events
- `limit`: effective requested page size
- `next_cursor`: opaque string or null
- `request_id`: server correlation UUID
