# Research: ACR1 Lifecycle and Delivery Safety

- Existing shutdown already stops queue admission first, but closed resources after a stuck task could be used by that task.
- Existing retries changed visibility only after failure; slow successful persistence had no heartbeat.
- The in-process queue already rejects stale receipt handles, so the worker can classify that boundary without exposing driver details.
- A small policy value object is sufficient for task registration; a general restart framework would exceed the feature scope.
