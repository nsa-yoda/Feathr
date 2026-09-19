# Feature 012 Quickstart

1. Run rebuild unit/failure tests: `.venv/bin/pytest -q tests/unit/test_search_rebuild.py tests/failure/test_search_rebuild.py`.
2. Review CLI safety: `.venv/bin/python -m event_platform.search.rebuild --help`.
3. With MongoDB and Elasticsearch configured, run `.venv/bin/pytest -q tests/integration/test_rebuild_live.py`.
4. Run Ruff, mypy, full unit, failure, and integration marker gates before merge.
