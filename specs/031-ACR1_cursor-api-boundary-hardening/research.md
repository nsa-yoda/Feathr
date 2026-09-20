# Research

Both Mongo and Elasticsearch cursor codecs previously used module-level random keys, invalidating cursors across workers. Event responses returned `CanonicalEvent`, leaking persistence hashes. Existing typed URL parsing provides a narrow place to reject credentials.
