# Feature 011 Research

- **Decision:** Use one explicit versioned mapping with `dynamic: false`, `flattened` metadata, and an analyzed metadata text field.
  **Rationale:** This preserves flexible metadata while preventing mapping explosion and supports case/diacritic-insensitive terms.
- **Decision:** Build all client search requests from bounded typed parameters and a fixed query template.
  **Rationale:** Raw JSON DSL would allow scripts, arbitrary fields, and unbounded execution.
- **Decision:** Encode only the two returned sort values and a filter digest in the signed cursor.
  **Rationale:** This provides deterministic continuation while preventing cursor reuse across different searches.
- **Decision:** Keep search behind a typed service port and return 503 on dependency or decode failures.
  **Rationale:** Elasticsearch is derived and must not be replaced by a Mongo fallback.
