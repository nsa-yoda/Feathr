.PHONY: format-check lint typecheck test-unit test-integration test-failure coverage smoke postman

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

coverage:
	uv run --locked coverage run --branch --source=src/event_platform -m pytest -q tests/unit
	uv run --locked coverage report --show-missing
	mkdir -p coverage
	uv run --locked coverage xml -o coverage/coverage.xml

smoke:
	./scripts/smoke

postman:
	./scripts/postman
