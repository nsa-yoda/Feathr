# Reviewer Experience

A reviewer should be able to clone/unpack the finished repository and evaluate it with minimal ceremony:

```bash
cp .env.example .env
docker compose up --build
```

The README must give URLs for UI, API docs, metrics, and health. Postman assets must be importable and runnable without hand-editing dozens of variables.

The UI and Postman collection are demonstration accelerators, not hidden dependencies. Every backend function remains directly testable through HTTP/pytest.
