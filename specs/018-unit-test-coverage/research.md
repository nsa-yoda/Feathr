# Feature 018 Research

## Existing evidence

- The isolated suite is `tests/unit` and is marked `unit` by pytest configuration.
- Queue, worker, retry, query, analytics, search, cache, and rate-limit tests already use fakes in most paths, so the remaining work can stay deterministic and service-free.
- `docs/testing-strategy.md` requires semantic assertions and treats coverage as a signal rather than a quality target.
- The repository currently has no coverage dependency or report target; the feature request explicitly requires one without inventing a percentage.

## Decisions

1. Keep tests close to the existing unit modules instead of creating a parallel test harness.
2. Use injected/manual clocks and deterministic jitter sources for timing behavior; never add wall-clock sleeps.
3. Retain fake storage, queue, cache, and search clients and assert both observable results and zero calls on rejected input.
4. Add a development-only `coverage` dependency and a `make coverage` target that runs the existing unit suite and emits terminal plus XML reports under `coverage/`.
5. Document measured output only when the command is run; README wording will explain that line/branch coverage cannot prove integration, live-service, browser, or semantic completeness.
6. Keep CI orchestration and Compose coverage publication in Feature 024; this feature supplies the reusable local report command.

## Alternatives rejected

- Adding a percentage threshold without measuring the current repository would create an unsupported acceptance claim.
- Replacing behavior tests with broad snapshot or mock-call assertions would weaken the semantic contract.
- Using real MongoDB, Elasticsearch, Redis, or wall-clock delays in unit tests would make the required isolated suite nondeterministic.
