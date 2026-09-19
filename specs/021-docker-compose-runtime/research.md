# Feature 021 Research

## Existing constraints

- `Dockerfile` already builds the FastAPI service as UID/GID 10001 and runs one Uvicorn worker.
- `frontend/Dockerfile` uses the non-root nginx image and serves `frontend/public`.
- `ServiceSettings` accepts `EVENT_PLATFORM_MONGO_URL`, `EVENT_PLATFORM_ELASTICSEARCH_URL`, and `EVENT_PLATFORM_REDIS_URL` with bounded dependency timeouts.
- Feature 019 integration tests use `MONGO_URI`, `ELASTICSEARCH_URL`, and `REDIS_URL` as externally supplied endpoints; Compose documentation must keep those test variables distinct from app runtime variables.
- Mongo change streams require a replica set; Mongo remains canonical, while Elasticsearch and Redis are optional/degraded dependencies.

## Decisions

1. Use Mongo 7.0, Elasticsearch 8.17.3, and Redis 7.4 Alpine image tags. These versions are explicit and compatible with the pinned Python clients.
2. Use a dedicated `feathr` bridge network and named volumes for Mongo, Elasticsearch, and Redis.
3. Use health checks for all long-running services. `mongo-init` waits for Mongo ping, calls `rs.initiate` only when needed, and verifies primary state before exiting successfully.
4. Use `service_completed_successfully` for app dependency on `mongo-init`, and `service_healthy` for Elasticsearch/Redis. No fixed sleeps are used.
5. Keep the UI static until Feature 023; nginx proxies `/api/` to the API by stripping the prefix.
6. Make smoke a bounded shell script with curl and jq only; it starts the stack with Compose, polls status, and emits only status codes and identifiers.

## Rejected alternatives

- A Mongo standalone container was rejected because change streams and the search projector require a replica set.
- `sleep N` startup ordering was rejected because it cannot distinguish a live process from a ready dependency.
- Host-installed Mongo/Elasticsearch/Redis were rejected because reviewers need one reproducible command.
