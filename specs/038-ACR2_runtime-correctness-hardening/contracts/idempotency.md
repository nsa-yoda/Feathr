# Idempotency Contract

- A reservation is scoped by authenticated client/tenant plus producer key and request fingerprint.
- A new reservation returns an owner token and generation.
- Queue admission failure releases only the matching owner reservation.
- Completion/enqueue transitions require the matching owner token and generation.
- Fresh duplicate requests observe `in_flight`; completed or enqueued duplicates replay the original event ID.
- Expired takeover is an atomic compare-and-set; exactly one contender wins.
