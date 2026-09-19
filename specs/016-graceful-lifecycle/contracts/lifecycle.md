# Lifecycle Contract

The supervisor exposes `start`, `request_shutdown`, `wait`, and `shutdown`
operations. `request_shutdown` first disables queue admission, then signals the
stop event. `shutdown` waits for managed tasks up to the configured grace
period, cancels remaining tasks, records queue depth, and closes resources in
the fixed order supplied at construction.

Unexpected managed-task exceptions produce `lifecycle.supervision_failure` and
the `failed` state. Cancellation after a deliberate shutdown is normal.
