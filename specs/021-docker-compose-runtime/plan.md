# Feature 021 Implementation Plan

## Architecture

Add a root `docker-compose.yml` with six services, one dedicated bridge network, and named data volumes. The app is built from the existing non-root `Dockerfile`; the UI is built from the existing non-root nginx image plus a small proxy configuration. A one-shot `mongo-init` service performs bounded, idempotent replica-set setup.

The app receives `EVENT_PLATFORM_MONGO_URL=mongodb://mongo:27017/?replicaSet=rs0`, `EVENT_PLATFORM_ELASTICSEARCH_URL=http://elasticsearch:9200`, and `EVENT_PLATFORM_REDIS_URL=redis://redis:6379/0`. Health checks expose liveness/readiness at `/health/live` and `/health/ready`, and Compose conditions ensure dependency readiness before app startup.

## Components and files

- `docker-compose.yml`: services, health checks, dependency conditions, volumes, network, ports, and resource limits.
- `docker/mongo-init.sh`: bounded Mongo ping/replica-set initialization.
- `frontend/nginx.conf`: non-root static server and `/api/` reverse proxy.
- `scripts/smoke`: clean-stack startup, bounded polling, ingestion, canonical/search/stats checks.
- `Makefile`: `smoke` target and Compose contract test target.
- `.env.example` and `README.md`: local configuration and operational quickstart.
- `tests/unit/test_compose_runtime.py`: static contract tests for Compose and smoke behavior.
- `src/event_platform/core/settings.py` and `src/event_platform/main.py`: bounded startup readiness retry if needed by runtime review.

## Verification

Run format, lint, type, unit, integration, failure, and Compose contract tests. Run `docker compose config`, `docker compose up --build -d`, `make smoke`, and `make postman` when Docker and the Feature 022 collection are available; record unavailable live gates explicitly.
