# Observability Contract

`X-Request-ID` accepts a canonical UUID at most 128 bytes and is generated when
invalid. Every response also returns `X-Operation-ID`. Problem documents retain
the existing RFC 9457-style request correlation field.

`GET /health/live` returns `{"status":"alive"}` without dependency calls.
`GET /health/ready` returns a typed snapshot and 503 when core readiness is
false. `GET /health/components` returns fixed safe component states. `GET
/metrics` returns Prometheus text with `text/plain; version=0.0.4`.
