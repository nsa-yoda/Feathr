# Feature 021 Research

## Existing constraints

- `Dockerfile` already builds the FastAPI service as UID/GID 10001 and runs one Uvicorn worker.
- `frontend/Dockerfile` uses the non-root nginx image and serves `frontend/public`.
- `ServiceSettings` accepts `EVENT_PLATFORM_MONGO_URL`, `EVENT_PLATFORM_ELASTICSEARCH_URL`, and `EVENT_PLATFORM_REDIS_URL` with bounded dependency timeouts.
- Feature 019 integration tests use `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL` as externally supplied endpoints; Compose documentation must keep those test variables distinct from app runtime variables.
- Mongo change streams require a replica set; Mongo remains canonical, while Elasticsearch and Redis are optional/degraded dependencies.

## Decisions

1. Use explicit stable image tags for MongoDB, Elasticsearch, Redis, Python, and the unprivileged Nginx frontend. The current Compose pins are MongoDB 8.3.11, Elasticsearch 9.5.4, Redis 8.10.1 Alpine, Python 3.14.7 slim, and Nginx 1.31.6 Alpine 3.24; the Python client floors in `pyproject.toml` match those service generations.
2. Use a dedicated `feathr` bridge network and named volumes for Mongo, Elasticsearch, and Redis.
3. Use health checks for all long-running services. `mongo-init` waits for Mongo ping, calls `rs.initiate` only when needed, and verifies primary state before exiting successfully.
4. Use `service_completed_successfully` for app dependency on `mongo-init`, and `service_healthy` for Elasticsearch/Redis. No fixed sleeps are used.
5. Keep the UI static until Feature 023; nginx proxies `/api/` to the API by stripping the prefix.
6. Make smoke a bounded shell script with curl and jq only; it starts the stack with Compose, polls status, and emits only status codes and identifiers.

## Rejected alternatives

- A Mongo standalone container was rejected because change streams and the search projector require a replica set.
- `sleep N` startup ordering was rejected because it cannot distinguish a live process from a ready dependency.
- Host-installed Mongo/Elasticsearch/Redis were rejected because reviewers need one reproducible command.
