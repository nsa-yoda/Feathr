# Research

The existing coordinator already gates swap on scan/index counts and renews leases between batches. Review gaps were fencing metadata, identifier lookup, and cleanup after a successful alias commit. The implementation preserves current adapter protocols and adds optional record metadata without changing the canonical Mongo source.
