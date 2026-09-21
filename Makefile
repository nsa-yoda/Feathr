.PHONY: format-check lint typecheck dependency-check test-unit test-functional test-integration test-integration-required test-acceptance-required test-e2e-required test-failure check-source-archive all coverage performance release-verify compose-config compose-up compose-down compose-reset smoke postman rebuild-status rebuild-demo

format-check:
	uv run --locked ruff format --check src tests

lint:
	uv run --locked ruff check src tests

typecheck:
	uv run --locked mypy

dependency-check:
	uv lock --check
	uv run --locked uv pip check

test-unit:
	uv run --locked pytest -q tests/unit

test-functional:
	uv run --locked pytest -q tests/functional -m functional

test-integration:
	uv run --locked pytest -q tests/integration -m integration --pass-with-no-tests

test-integration-required:
	./scripts/test-integration-required

test-acceptance-required:
	MONGO_URI="$${MONGO_URI:?MONGO_URI is required}" ELASTICSEARCH_URL="$${ELASTICSEARCH_URL:?ELASTICSEARCH_URL is required}" REDIS_URL="$${REDIS_URL:?REDIS_URL is required}" ./scripts/test-acceptance-required

test-e2e-required:
	E2E_BASE_URL="$${E2E_BASE_URL:?E2E_BASE_URL is required}" uv run --locked pytest -q tests/e2e -m e2e

check-source-archive:
	./scripts/check-source-archive

test-failure:
	uv run --locked pytest -q tests/failure -m failure --pass-with-no-tests

all: format-check lint typecheck dependency-check test-unit test-functional test-integration test-failure

coverage:
	uv run --locked coverage run --branch --source=src/event_platform -m pytest -q tests/unit tests/functional tests/failure
	uv run --locked coverage report --show-missing --fail-under=90
	mkdir -p coverage
	uv run --locked coverage xml -o coverage/coverage.xml

performance:
	uv run --locked python scripts/performance

release-verify:
	./scripts/release-verify

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
	@echo 'Guarded rebuild command (requires MongoDB replica set and Elasticsearch):'
	@echo 'uv run --locked python -m event_platform.cli search rebuild --confirm'
	@echo 'Use make rebuild-status to inspect the latest durable state.'
