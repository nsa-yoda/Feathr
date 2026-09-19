# Feature 009 Data Model

## AnalyticsRange

- `start`: UTC-aware datetime, inclusive.
- `end`: UTC-aware datetime, inclusive.
- `maximum_span`: 366 days.

## StatsPoint

- `bucket`: UTC-aware truncated datetime.
- `event_type`: canonical event type.
- `count`: positive integer.

## StatsResponse

- `bucket`: `hour | day | week`.
- `timezone`: literal `UTC`.
- `start`, `end`: effective inclusive UTC range.
- `points`: ordered `StatsPoint[]`.
- `request_id`: UUID correlation identifier.

## Aggregation guard

- The canonical Mongo aggregation uses a 5-second `maxTimeMS` deadline in addition to the 10,000-point response cap. A deadline failure is translated to the shared safe 503 dependency response; the service never returns partial counts.
