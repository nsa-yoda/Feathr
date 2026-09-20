# Idempotency Contract

- Matching completed retries return the original event ID and queued outcome.
- A different fingerprint for the same scoped key returns problem 409.
- A reservation still in flight returns problem 409; expired reservations may be recovered within the replay window.
- Registry dependency failure returns safe retryable 503.
