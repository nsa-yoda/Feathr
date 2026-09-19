# Feature 021 Quickstart

```bash
cp .env.example .env
docker compose up --build -d
make smoke
```

The smoke command leaves the Compose project running when a check fails so a
reviewer can inspect `docker compose ps` and service health. Reset a failed or
successful run with `docker compose down -v`.

Open `http://localhost:3000` for the UI shell, `http://localhost:8000/docs` for OpenAPI, and `http://localhost:8000/health/ready` for dependency readiness.

To remove containers and all local data:

```bash
docker compose down -v
```

The live Compose gates require Docker, curl, and jq. Static contract tests and `docker compose config` remain useful when Docker cannot run.
