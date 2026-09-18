# Implementation Plan: Async Ingestion API

Wire a FastAPI route to the existing EventInput/CanonicalEvent and InProcessQueue boundaries. Add bounded queue settings to the validated service configuration and create/close the queue in application lifespan. Keep Mongo out of the request path.
