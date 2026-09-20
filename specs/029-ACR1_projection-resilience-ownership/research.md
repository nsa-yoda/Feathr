# Research

The projector already isolates search failures from Mongo ingestion and persists checkpoints after writes. The review gap was concurrent ownership: a stale process could replace a newer checkpoint. A generation predicate at the storage boundary provides fencing without introducing a broker or unbounded task fan-out.
