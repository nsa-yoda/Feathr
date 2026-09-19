# Feature 019 Research Notes

## Existing evidence

- `tests/integration/` already contains real MongoDB, Elasticsearch, and Redis tests, but setup and cleanup are duplicated and several scenarios bypass the HTTP app lifecycle.
- `main.py` constructs the configured Elasticsearch client and projector but does not currently assign an `ElasticsearchSearchService` to `app.state.search_service`; the search route therefore returns a safe 503 in a configured app.
- Existing projection tests use a fixed `asyncio.sleep(0.05)` polling interval without a shared deadline diagnostic.
- Feature 021 owns Docker Compose startup, so this feature should consume explicit endpoint variables and skip clearly when services are absent.

## Decisions

1. Use a small integration support module with unique namespace allocation and a bounded async `poll_until` helper. It must avoid fixed long sleeps and include a safe last-observation timeout message.
2. Keep service-gated skips at test entry after endpoint variables are checked. A ping or capability failure is a skip with the exception type, not a false success.
3. Use real async PyMongo, Elasticsearch, and Redis clients. No mock can satisfy a Feature 019 scenario.
4. Test app-level ingestion/query/realtime and search wiring where lifecycle ownership is part of the scenario; retain lower-level real-service tests for focused service behavior.
5. Set `app.state.search_service` from the configured Elasticsearch client and delete it during lifespan teardown; this is the minimal production correction required by FR-010.
6. Namespaces use UUID suffixes and cleanup is attempted in `finally` blocks, with credential-safe diagnostics.
