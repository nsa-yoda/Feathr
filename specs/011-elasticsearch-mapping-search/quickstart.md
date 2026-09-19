# Feature 011 Quickstart

1. Run mapping/search unit tests: `.venv/bin/pytest -q tests/unit/test_search_mapping.py tests/unit/test_search.py`.
2. Run failure tests: `.venv/bin/pytest -q tests/failure/test_search_failures.py`.
3. With Elasticsearch configured, run `.venv/bin/pytest -q tests/integration/test_search_live.py`.
4. Run Ruff and mypy gates before merge.
