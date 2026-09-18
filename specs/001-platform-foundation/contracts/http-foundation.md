# HTTP Contract: Platform Foundation

The generated FastAPI OpenAPI document is the runtime description. This contract fixes the foundation semantics that the implementation and tests must preserve. Later feature contracts add application endpoints.

## Endpoints

| Method and path | Successful response | Notes |
|---|---|---|
| `GET /health/live` | `200`, `application/json`, `{"status":"alive"}` | Indicates only that the base process/event loop serves requests. It does not claim datastore readiness. |
| `GET /openapi.json` | `200`, OpenAPI JSON | Describes available routes and declared problem responses. |
| `GET /docs` | Interactive API documentation | Standard reviewer entrypoint. |

All HTTP responses, including errors, include a server-generated `X-Request-ID` UUID. The service does not accept caller-supplied request IDs in Feature 001.

## Problem document

Errors use `Content-Type: application/problem+json` with exactly these required members in the foundation contract:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "The requested resource was not found.",
  "instance": "/missing",
  "error_code": "route_not_found",
  "request_id": "f8f0fb30-4824-4e15-8b63-70cceeb58a48"
}
```

`status` equals the HTTP status; `request_id` equals `X-Request-ID`; `instance` contains only the request path. `type`, `title`, `status`, `detail`, and `instance` follow RFC 9457. `error_code` and `request_id` are documented extension members. Generic `about:blank` problems use the HTTP status title. Application-specific problem types may be added by later features when they have stable documentation URIs.

| Condition | HTTP status | Title | `error_code` | Detail policy |
|---|---:|---|---|---|
| Unknown route | 404 | Not Found | `route_not_found` | Safe fixed message. |
| Request validation | 422 | Unprocessable Content | `request_validation_failed` | Safe summary without rejected values or body. |
| Unhandled failure | 500 | Internal Server Error | `internal_error` | Generic fixed message. |
| Other framework HTTP error | Its HTTP status | Standard status title | `http_<status>` | Safe status-level message; preserve protocol-required headers such as `Allow` on 405. |

The request validation case is verified with a test-only route until a production route accepts typed input. An unexpected-error test also uses a test-only route, with exception re-raising disabled in the test client. Production debug tracebacks remain disabled. Route OpenAPI declarations must describe the problem media type rather than claiming the framework's default validation shape.

## Startup failure

An invalid `EVENT_PLATFORM_ENV` or `EVENT_PLATFORM_LOG_LEVEL` rejects startup before serving requests. The diagnostic names the setting and validation category, without its supplied value. It is a process startup failure, not an HTTP problem response.

## Deferred HTTP scope

Readiness, component health, metrics, event ingestion, queries, search, stats, cache, and rate-limit responses belong to their numbered features. The liveness response here does not certify any of those capabilities.
