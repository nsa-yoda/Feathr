# Security Contract

## Body limit

`POST` and other body-bearing requests pass through a receive wrapper. A declared or accumulated body over `request_body_max_bytes` returns `413` with `application/problem+json`, `error_code=request_body_too_large`, and the generated request ID. The body and raw parser error are never returned.

Raw query strings over `request_query_max_bytes` (8 KiB by default) return `414` with `error_code=request_query_too_large` before route parsing. Both synthetic responses carry request and operation correlation headers.

## CORS

When `cors_allowed_origin` is null, no CORS allow-origin response is emitted. When configured, only that exact origin is allowed, with `GET`, `POST`, and `OPTIONS` methods and `Content-Type`, `X-Request-ID`, and `Idempotency-Key` request headers. Credentials are not enabled.

## Security headers

Every normal API response, including problem responses, carries the documented security headers.

## Trust and diagnostics

Forwarding identity is direct-peer by default. Startup and runtime errors expose stable error categories and types only; credentials, URLs containing credentials, request bodies, stack traces, and dependency messages are excluded.
