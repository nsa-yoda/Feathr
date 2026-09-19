# Feature 012 Research

- **Decision:** Use a Mongo compare-and-set lease with owner and expiry fields.
  **Rationale:** A durable lease survives process restarts and lets the next operator recover a stale run without changing the serving alias.
- **Decision:** Use Elasticsearch aliases API with one atomic actions request for swap.
  **Rationale:** Remove/add in one request prevents an observable no-alias window.
- **Decision:** Activate the Feature 010 target callback before scanning and clear it in `finally`.
  **Rationale:** Every live event after activation reaches the target; cleanup remains deterministic on failure/cancellation.
- **Decision:** Verify scanned count equals target count and unresolved failures are zero before swap.
  **Rationale:** Count equality plus failure-free bulk state is a bounded safety gate for this single-source rebuild.
- **Decision:** Retain the old index through an explicit rollback deadline; cleanup is a separate operation.
  **Rationale:** A failed or suspect swap remains reversible without deleting the previous serving generation.
