# Functional tests

Functional tests exercise the public HTTP contract through FastAPI's ASGI
boundary while keeping external services disabled. They complement isolated
unit tests with real routing, middleware, validation, and problem responses.

Run them with `make test-functional`.
