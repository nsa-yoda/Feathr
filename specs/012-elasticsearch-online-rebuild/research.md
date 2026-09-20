# Feature 012 Research

- **Decision:** Use a Mongo compare-and-set lease with owner and expiry fields.
  **Rationale:** A durable lease survives process restarts and lets the next operator recover a stale run without changing the serving alias.
- **Decision:** Use Elasticsearch aliases API with one atomic actions request for swap.
  **Rationale:** Remove/add in one request prevents an observable no-alias window.
- **Decision:** Activate the Feature 010 target callback before scanning and clear it in `finally`.
  **Rationale:** Every live event after activation reaches the target; cleanup remains deterministic on failure/cancellation.
- **Decision:** Capture a majority-consistent Mongo ObjectId `backfill_upper_bound` after candidate dual-write activation, but use the ordered change-stream operation position as the authoritative convergence watermark; reconcile canonical event IDs before swap.
  **Rationale:** ObjectIds can be allocated before an insert commits and therefore cannot order concurrent writes. The live change stream covers those late commits, while identity comparison protects against missing or wrong documents; count equality alone cannot detect replacement documents or live-write races.
- **Decision:** Retain the old index through an explicit rollback deadline; cleanup is a separate operation.
  **Rationale:** A failed or suspect swap remains reversible without deleting the previous serving generation.
