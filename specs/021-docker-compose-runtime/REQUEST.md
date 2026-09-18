# Feature Request: Docker Compose Runtime

## Goal

A reviewer uses one ordinary Compose command to start the complete stack.

## Services

- app: one FastAPI/Uvicorn process, includes local queue and background workers;
- mongo: pinned Mongo image with replica set enabled;
- mongo-init: idempotent one-shot replica set initialization/health coordination if needed;
- elasticsearch: pinned compatible single-node image with local-development settings;
- redis: pinned image, configured health check and local password if chosen;
- ui: multi-stage-built React app served by non-root-capable nginx or equivalent and reverse proxies `/api` to app if selected.

## Requirements

- healthchecks and dependency startup sequencing based on health, not arbitrary sleep;
- named volumes where useful;
- `.env.example` with documented non-secret local defaults;
- app waits/retries boundedly for replica-set readiness;
- no multiple Uvicorn workers;
- resource limits/settings reasonable enough for common reviewer laptops;
- clear `down -v` reset instructions;
- build cache friendly Dockerfiles, non-root final user for app/UI where feasible.

## Smoke

Provide a command/script that starts clean stack, waits on readiness with deadline, posts an event, polls canonical query/search, checks realtime stats, and exits nonzero on failure.


## Dependencies

003, 010, 011, 013, 016, 017

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
