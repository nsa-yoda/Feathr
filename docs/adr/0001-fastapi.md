# ADR 0001: Use FastAPI for the HTTP service

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Use FastAPI with Pydantic v2 models and lifespan-managed async dependencies.

## Rationale

The workload is I/O heavy and integrates async Mongo, Elasticsearch, Redis, and background tasks. FastAPI provides typed validation, OpenAPI generation, ASGI lifecycle support, and a natural async programming model while remaining within the requested stack.

## Consequences

Handlers and infrastructure adapters must avoid blocking I/O. OpenAPI becomes a useful reviewer artifact. Flask is not used because adding equivalent async/lifecycle/schema machinery would increase assessment code without demonstrating additional system reasoning.
