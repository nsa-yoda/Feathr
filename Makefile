.PHONY: format-check lint typecheck test-unit test-integration test-failure

format-check:
	uv run --locked ruff format --check src tests

lint:
	uv run --locked ruff check src tests

typecheck:
	uv run --locked mypy

test-unit:
	uv run --locked pytest -q tests/unit

test-integration:
	uv run --locked pytest -q tests/integration -m integration --pass-with-no-tests

test-failure:
	uv run --locked pytest -q tests/failure -m failure --pass-with-no-tests
