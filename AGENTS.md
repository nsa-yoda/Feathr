# AGENTS.md — Codex Operating Contract

Read `CODEX-HANDOFF.md` first. This repository is Spec Kit driven.

## Priority of authority

When instructions conflict, use this order:

1. `.specify/memory/constitution.md`
2. locked decisions in `CODEX-HANDOFF.md`
3. accepted ADRs under `docs/adr/`
4. `ARCHITECTURE.md` and supporting architecture documents
5. the active feature's accepted `spec.md`
6. the active feature's accepted `plan.md`
7. the active feature's `tasks.md`
8. implementation convenience

Never silently weaken a higher-priority requirement to simplify code.

## Engineering behavior

- Prefer small, explicit modules with clear ownership over clever abstraction.
- Keep domain/API contracts separate from Mongo, Elasticsearch, Redis, and queue implementations.
- Use typed models at boundaries.
- Make clocks, random jitter, and retry timing injectable/testable where practical.
- All network clients are created and closed in application lifespan management.
- Never block the async event loop with synchronous network I/O.
- Never catch broad exceptions without classification, structured logging, and a deliberate disposition.
- Never log full event metadata, credentials, Redis passwords, Mongo credentials, or request bodies by default.
- Do not make Elasticsearch or Redis a prerequisite for durable event persistence.
- Tests are part of every feature, not a cleanup phase.
- Avoid comments that restate code. Comments should explain invariants, failure semantics, or non-obvious tradeoffs.
- Update docs whenever behavior or guarantees change.

## Required commands before a feature is accepted

Use the project commands eventually implemented by Feature 001/022, expected to include equivalents of:

```bash
make format-check
make lint
make typecheck
make test-unit
make test-integration
make test-failure
```

At repository completion, also run:

```bash
docker compose config
docker compose up --build -d
make smoke
make postman
```

If exact target names evolve, keep the same intent and document the final commands in README.
