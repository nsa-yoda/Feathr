# Feature 012 Research

- **Decision:** Use a Mongo compare-and-set lease with owner and expiry fields.
  **Rationale:** A durable lease survives process restarts and lets the next operator recover a stale run without changing the serving alias.
- **Decision:** Use Elasticsearch aliases API with one atomic actions request for swap.
  **Rationale:** Remove/add in one request prevents an observable no-alias window.
- **Decision:** Activate the Feature 010 target callback before scanning and clear it in `finally`.
  **Rationale:** Every live event after activation reaches the target; cleanup remains deterministic on failure/cancellation.
- **Decision:** Capture the maximum Mongo ObjectId after candidate dual-write activation, backfill through that boundary, wait for the projector source-position marker to converge, and reconcile canonical event IDs before swap.
  **Rationale:** A durable high-water boundary and identity comparison protect against missing or wrong documents; count equality alone cannot detect replacement documents or live-write races.
- **Decision:** Retain the old index through an explicit rollback deadline; cleanup is a separate operation.
  **Rationale:** A failed or suspect swap remains reversible without deleting the previous serving generation.
