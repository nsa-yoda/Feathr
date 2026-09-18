# Distributed Event Processing Platform

> **Handoff state:** architecture/specification pack. Codex must turn this into the finished assessment repository using `CODEX-HANDOFF.md` and Spec Kit.

A production-oriented event ingestion, processing, search, analytics, caching, and reviewer-demo platform built with FastAPI, MongoDB, Elasticsearch, Redis, and an assessment-mandated in-process SQS-style queue.

## Target reviewer quick start

The finished repository must support a workflow no more complicated than:

```bash
cp .env.example .env
docker compose up --build
```

README must then list:

- Demo UI URL
- FastAPI/OpenAPI URL
- health URLs
- Prometheus metrics URL
- Postman import/run instructions
- unit/integration/failure test commands

## Required final sections

Codex must replace this planning README with a complete submission README containing:

1. Project overview and key guarantees
2. Architecture summary and link to `ARCHITECTURE.md`
3. Quick start / Docker Compose
4. Configuration table
5. API endpoint documentation with examples
6. Queue semantics and `202` durability caveat
7. Testing philosophy and commands
8. Postman reviewer workflow
9. Demo UI guide
10. Operational/health/metrics guide
11. Elasticsearch rebuild command/behavior
12. SQS production migration summary
13. Known constraints/tradeoffs
14. **AI in My Workflow** — tools used, concrete contributions, corrections/pushback, and how AI changed speed/quality, grounded in `docs/ai-workflow-log.md`

Do not leave generic AI boilerplate. The panel specifically wants evidence of strategic AI use and human judgment.
