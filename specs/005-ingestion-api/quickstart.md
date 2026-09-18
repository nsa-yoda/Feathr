# Feature 005 Quickstart

`POST /events` with a valid Feature 002 payload returns 202 and a queued event ID. The response request ID is always the server-generated `X-Request-ID`. Queue saturation returns 503 and `Retry-After: 1`.
