# Data Model: ACR1 Lifecycle and Delivery Safety

- `TaskPolicy`: bounded `criticality`, `restart_limit`, and `restart_backoff`.
- `WorkerMetrics`: inserted, retry, dead-letter, visibility-renewal, and ownership-loss counters.
- `LifecycleSnapshot`: state, acceptance, active tasks, queue depth, and failure type; an attached task timeout leaves state failed and resources isolated.
