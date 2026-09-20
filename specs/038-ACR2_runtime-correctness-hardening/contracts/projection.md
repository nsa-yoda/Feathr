# Projection Contract

- A projector must hold a Mongo lease identified by owner and fencing generation.
- Only the current owner may renew or checkpoint.
- Checkpoints are monotonic and are written only after Elasticsearch acknowledges the corresponding bounded batch.
- Elasticsearch failure marks search degraded and schedules retry/rebuild; it does not stop canonical Mongo ingestion.
