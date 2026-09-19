# Feature 016 Data Model

## LifecycleSnapshot

`state` is one of `starting`, `running`, `draining`, `stopped`, or `failed`;
`accepting` is a boolean; `active_tasks` is a bounded tuple of names;
`queue_depth` is a non-negative integer; `failure_type` is an optional exception
class name.

## Managed resource

Each resource has a stable name and an async close callback. Close callbacks are
invoked once in the declared order and failures are logged with the safe
resource name and exception type.
