# Feature 014 Data Model

## RoutePolicy

`name`, `capacity` (positive integer), `refill_per_second` (positive decimal), `cost` (positive integer), and `exempt`.

## BucketState

`identity`, `route_class`, `tokens`, `last_refill`, and `last_seen`; identity and class are the only key dimensions. Redis stores a compact hash/string representation with bounded expiry. Local state stores the same values in an ordered bounded map.

## RateDecision

`allowed`, `limit`, `remaining`, `reset_at`, `retry_after`, and `backend` (`redis` or `local`). It is response metadata and is never persisted as an authoritative business record.
