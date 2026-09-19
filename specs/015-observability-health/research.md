# Feature 015 Research

1. A local registry avoids adding a runtime metrics dependency while preserving
   the Prometheus text contract needed by reviewers.
2. Health probes are injected callables because this repository owns several
   optional external adapters and tests must distinguish unavailable services
   from application logic failures.
3. Canonical UUID request IDs prevent header injection and high-cardinality
   correlation values while retaining useful cross-service tracing.
