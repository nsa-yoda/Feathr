# ADR 0002: Use PyMongo Async API instead of Motor

**Status:** Accepted  
**Date:** 2026-09-18


## Decision

Use `pymongo.AsyncMongoClient` and PyMongo's async API.

## Rationale

MongoDB has deprecated Motor in favor of the PyMongo Async API. Starting a new 2026 codebase on Motor would create immediate migration debt. AsyncMongoClient matches the ASGI I/O model.

## Consequences

One AsyncMongoClient belongs to the application's event loop and is lifespan-managed. Tests and repository abstractions must use the async API consistently.
