# Implementation Plan: ACR1 Production Security Boundary

## Summary

Add a fail-closed production bearer-token boundary, reject placeholder operator credentials, require shared cursor/Mongo production configuration, and emit HSTS alongside the existing browser security headers. Keep local/test convenience behavior unchanged.

## Design

- `production_api_token` is deployment-supplied, bounded, and rejected when missing or placeholder in production.
- Middleware exempts only cheap liveness and returns a safe RFC 9457-shaped 401 for protected traffic.
- Security headers add HSTS only in production; CORS remains exact-origin and credential-free.
- Rate limiter local fallback remains bounded/conservative and observable.
