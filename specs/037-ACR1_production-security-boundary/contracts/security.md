# Production Security Contract

- Production requires Mongo URL, shared cursor key, and non-placeholder API token.
- All routes except `/health/live` require `Authorization: Bearer <token>`.
- Production responses include HSTS; CORS remains exact-origin and credentials disabled.
- Limiter Redis outage uses bounded local fallback and emits degraded observability.
