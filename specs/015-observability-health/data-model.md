# Feature 015 Data Model

## ComponentHealth

`state` is one of `healthy`, `degraded`, or `unhealthy`; `detail` is one of the
fixed safe values `ok`, `degraded`, `unavailable`, `not_configured`,
`probe_failed`, or `unknown`.

## HealthSnapshot

`status` is the aggregate state and `components` contains the fixed Mongo,
Elasticsearch, Redis, queue, persistence-worker, and search-projector keys.

## Metric sample

Metric names are fixed families and labels are bounded route, method, status,
component, backend, and outcome values. Request IDs and event IDs never appear.
