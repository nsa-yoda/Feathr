# Feature 019 Data Model

## IntegrationNamespace

- `suffix`: unique opaque identifier
- `database`: isolated Mongo database name
- `collection`: isolated event collection name
- `checkpoint_collection`: isolated projector checkpoint collection
- `alias`: isolated Elasticsearch serving alias
- `target_index`: isolated rebuild target/index prefix
- `redis_prefix`: isolated Redis key prefix

## PollObservation

- `operation`: safe operation label
- `deadline`: monotonic deadline
- `interval`: bounded polling interval
- `attempts`: number of observations
- `last_observation`: sanitized status or count, never credentials or full payloads
