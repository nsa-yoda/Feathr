.PHONY: format-check lint typecheck test-unit

format-check:
	uv run --locked ruff format --check src tests

lint:
	uv run --locked ruff check src tests

typecheck:
	uv run --locked mypy

test-unit:
	uv run --locked pytest -q tests/unit
