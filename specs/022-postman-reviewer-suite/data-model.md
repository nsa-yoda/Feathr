# Feature 022 Variable Model

| Variable | Scope | Meaning |
|---|---|---|
| `baseUrl` | environment | API origin, default `http://localhost:8000` |
| `pollDeadlineMs` / `pollIntervalMs` | environment | bounded eventual-consistency controls |
| `eventId` / `eventUserId` | environment | captured ingestion identity used by later folders |
| `idempotencyKey` | environment | unique run key sent to ingestion and dedup requests |
| `eventTimestamp` | environment | current UTC event timestamp |
| `nextCursor` | environment | captured canonical query cursor |
| `rateLimitBurst` | environment | configurable optional burst count |

No credentials or arbitrary event payloads are stored in the environment file.
