# Feature 022 Research

## Existing contracts

- The API exposes `/events`, `/events/search`, `/events/stats`, `/events/stats/realtime`, `/health/live`, `/health/ready`, `/health/components`, and `/metrics`.
- Ingestion returns `202` with `event_id`, `status`, and `request_id`; `Idempotency-Key` is optional but the suite sends a unique value.
- Canonical query and search are eventually consistent; Mongo is canonical and Elasticsearch is a projection.
- Realtime responses expose `X-Cache` with `HIT`, `MISS`, or `BYPASS` outcomes.
- Problem responses expose `status`, `detail`, `error_code`, `request_id`, and `instance`.

## Decisions

1. Use Postman Collection v2.1 and a separate v2.1 environment with `baseUrl`, `pollDeadlineMs`, `pollIntervalMs`, `eventId`, `eventUserId`, `idempotencyKey`, `nextCursor`, and rate-limit controls.
2. Use numbered folders exactly as requested; requests are safe to run in order and use unique timestamps/user suffixes.
3. Use `pm.sendRequest` polling with a monotonic wall-clock deadline and configurable interval. No fixed sleep command is used.
4. Treat healthy and safe degraded responses as distinct assertions. A `503` is only accepted when its problem fields are present.
5. Provide a `scripts/postman` wrapper that uses installed Newman and fails with exit 2 if Newman is unavailable.
