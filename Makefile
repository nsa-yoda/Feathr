.PHONY: format-check lint typecheck test-unit test-integration test-integration-required test-failure check-source-archive all coverage compose-config compose-up compose-down compose-reset smoke postman rebuild-status rebuild-demo

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

test-integration-required:
	./scripts/test-integration-required

check-source-archive:
	./scripts/check-source-archive

test-failure:
	uv run --locked pytest -q tests/failure -m failure --pass-with-no-tests

all: format-check lint typecheck test-unit test-integration test-failure

coverage:
	uv run --locked coverage run --branch --source=src/event_platform -m pytest -q tests/unit
	uv run --locked coverage report --show-missing
	mkdir -p coverage
	uv run --locked coverage xml -o coverage/coverage.xml

compose-config:
	docker compose --env-file .env.example config --quiet

compose-up:
	docker compose --env-file .env.example up --build -d

compose-down:
	docker compose --env-file .env.example down

compose-reset:
	docker compose --env-file .env.example down -v

smoke:
	./scripts/smoke

postman:
	./scripts/postman

rebuild-status:
	uv run --locked python -m event_platform.cli search rebuild-status

rebuild-demo:
	@echo 'Guarded rebuild command (requires the application dependency harness):'
	@echo 'uv run --locked python -m event_platform.cli search rebuild --confirm'
	@echo 'Use make rebuild-status to inspect the latest durable state.'
