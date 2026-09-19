# Feature 017 Data Model

## SecuritySettings

| Field | Type | Contract |
| --- | --- | --- |
| `request_body_max_bytes` | integer | 1,024–16,777,216; default 1,048,576 |
| `request_query_max_bytes` | integer | 256–65,536; default 8,192; raw query strings above this return 414 |
| `cors_allowed_origin` | string or null | exact HTTP(S) origin, no wildcard/path/userinfo; null disables CORS |
| `dependency_timeout_seconds` | number | 0.1–30.0; default 5.0 |
| `rate_limit_trusted_proxy_hops` | integer | 0–10; zero ignores forwarding headers |

## Bounded request

The middleware tracks bytes received for one HTTP request. It rejects a declared `Content-Length` above the configured limit before passing the request downstream and rejects streamed accumulation above the same limit. It never logs body bytes.

## Security header set

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`

The application does not emit HSTS for local HTTP because browsers cache HSTS policy across future requests; production TLS termination may add it at the edge.
