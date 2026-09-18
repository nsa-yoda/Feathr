# Data Model: Platform Foundation

Feature 001 has no persisted business entities. These are typed in-process and HTTP-boundary models. Later features add event and infrastructure models under their owning packages.

## ServiceSettings

| Field | Type | Default | Validation and ownership |
|---|---|---|---|
| `env` | `local | test | production` | `local` | Read from `EVENT_PLATFORM_ENV`; reject unknown values at startup. |
| `log_level` | `DEBUG | INFO | WARNING | ERROR` | `INFO` | Read from `EVENT_PLATFORM_LOG_LEVEL`; reject unknown values at startup. |

Settings are created during lifespan startup or injected into the app factory by a test. The foundation does not require MongoDB, Elasticsearch, Redis, or queue credentials. When later features add settings, required values must be validated before the corresponding client starts. Secrets use a redacted secret type and startup diagnostics expose setting names and failure categories only, never input values.

**Relationships**: One validated settings object belongs to one app lifespan. Routes and later clients read that object through app-owned state/dependencies; they do not construct it independently.

## RequestContext

| Field | Type | Validation |
|---|---|---|
| `request_id` | server-generated UUID string | Generated once per request; reflected in `X-Request-ID` and error bodies. Inbound identifiers are not trusted in this foundation slice. |
| `path` | URI path | Used as the problem `instance`; exclude query parameters and bodies to avoid reflecting sensitive input. |

**Relationships**: One context belongs to one HTTP request. All exception handlers use the same request ID supplied by middleware.

## ProblemResponse

| Field | Type | Validation |
|---|---|---|
| `type` | URI reference | `about:blank` for generic foundation HTTP status problems. |
| `title` | non-empty string | Standard title for the HTTP status; does not contain user input. |
| `status` | integer | Must equal the HTTP response status. |
| `detail` | string | Safe, bounded explanation; no raw exception, stack trace, secret, or request body. |
| `instance` | URI path | The current request path, without query string. |
| `error_code` | stable string | Machine-readable application code; see the HTTP contract. |
| `request_id` | UUID string | Matches the response header and request context. |

**Relationships**: One error response is constructed from an error classification and one request context. The initial classifications are route not found, request validation failed, unexpected internal error, and generic HTTP errors (including method not allowed). Later features add stable codes without changing this shape.

## Application lifecycle

This is a state machine, not a persisted entity or a required model class:

```text
constructed -> starting -> serving -> stopping -> stopped
                     └──> startup failed
```

- `constructed`: factory has registered routes, middleware, and handlers; no dependency client is open.
- `starting`: validate settings and initialize only startup-owned resources. Feature 001 initializes no network clients.
- `serving`: liveness and OpenAPI are available.
- `stopping`: stop accepting new work and release owned resources in bounded shutdown. In Feature 001 this is a clean no-op resource teardown.
- `startup failed`: invalid settings prevent serving and produce a sanitized diagnostic.

Later features extend startup/shutdown ownership without changing these transitions. See [the HTTP contract](contracts/http-foundation.md) for external behavior and [the plan](plan.md) for package ownership.
