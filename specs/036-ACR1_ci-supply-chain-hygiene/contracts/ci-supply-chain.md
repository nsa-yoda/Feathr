# CI and Supply Chain Contract

- Optional local skips use `make test-integration`.
- Required configured integration runs use `make test-integration-required` and fail on missing endpoints or skips.
- `make check-source-archive` rejects tracked caches, bytecode, editor/platform metadata, and missing core inputs.
