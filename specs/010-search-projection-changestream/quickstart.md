# Feature 010 Quickstart

1. Run the unit suite: `.venv/bin/pytest -q tests/unit/test_search_projection.py`.
2. With MongoDB replica set and Elasticsearch running, set `MONGO_URI` and `ELASTICSEARCH_URL` and run `.venv/bin/pytest -q tests/integration/test_search_projection_integration.py`.
3. To exercise failure behavior, run `.venv/bin/pytest -q tests/failure/test_search_projection_failure.py`.
4. Inspect `ProjectionStatus` after startup, successful projection, ES failure, and invalid resume history. Confirm no resume token or raw driver message appears.
