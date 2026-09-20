# Data Model

`PublicEvent` contains only event identity, producer fields, metadata, timestamp, and ingestion time. Cursor payload remains versioned and filter-bound; keys are configured bytes with one current and one previous overlap key.
