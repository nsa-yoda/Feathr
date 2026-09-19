# Feature 021 Runtime Data Model

| Entity | Role | Durable location |
|---|---|---|
| Mongo replica set | Canonical events, checkpoints, rebuild state | `mongo_data` volume |
| Elasticsearch node | Rebuildable search projection | `elasticsearch_data` volume |
| Redis instance | Rate-limit and realtime cache acceleration | `redis_data` volume |
| Compose network | Service discovery and isolation | Docker-managed |
| Smoke event | Ephemeral acceptance probe | Mongo canonical collection |

The Compose contract does not add domain fields. Runtime URLs and credentials are configuration values, while event payload validation remains owned by the API domain contract.
