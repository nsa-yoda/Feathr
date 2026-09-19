# Feature 012 Implementation Plan: Online Elasticsearch Rebuild

## Summary

Add a typed rebuild coordinator, Mongo-backed lease/state adapter, Elasticsearch generation/alias adapter, read-only status route, and guarded CLI contract. The coordinator activates Feature 010 dual-write before bulk scanning and swaps the stable alias only after verification.

## Technical Context

- Python 3.12+, FastAPI, Pydantic v2, PyMongo Async, official async Elasticsearch client.
- `src/event_platform/search/mapping.py` is authoritative for mapping and physical generation names.
- The coordinator consumes an async canonical event source and emits typed progress records.
- Network dependency failures are classified and never leak raw driver details.

## Constitution Check

- Mongo remains canonical; Elasticsearch is derived and rebuildable.
- Lease, checkpoint, and rebuild state are operational records with typed boundaries.
- Alias swap is atomic and old generations are retained.
- Tests, logs, status, and documentation are part of the feature.

## Design

1. `search/rebuild.py` owns models, ports, coordinator, failure classification, and CLI parser.
2. `storage/rebuilds.py` owns Mongo compare-and-set lease/state persistence.
3. `search/elasticsearch_rebuild.py` owns index creation, bulk, alias resolution/swap, and count adapters.
4. `api/routes/rebuild.py` exposes read-only status only.
5. `main.py` includes the status router; lifecycle injection remains explicit.
