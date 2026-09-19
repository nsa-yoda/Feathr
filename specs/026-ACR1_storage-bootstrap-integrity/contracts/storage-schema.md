# Contract: Versioned Mongo Storage Bootstrap

## Operator CLI

```text
python -m event_platform.cli storage bootstrap
python -m event_platform.cli storage verify
```

Both commands load `EVENT_PLATFORM_MONGO_URL`, `EVENT_PLATFORM_MONGO_DATABASE`, collection settings, and the existing dependency timeout. A missing Mongo URL is a configuration error. Commands return `0` only after complete verification and return a non-zero status with a safe classified log on failure.

`bootstrap` may create declared indexes and the version-1 schema marker. It performs no destructive migration and never drops or rewrites an incompatible index.

`verify` is read-only. It validates the schema marker and every required live index definition.

## Application Startup

When `EVENT_PLATFORM_MONGO_URL` is configured, lifespan startup MUST run the same read-only verification before creating persistence or projection tasks. Any verification failure aborts startup and closes the created Mongo client.

When `EVENT_PLATFORM_ENV=production`, `EVENT_PLATFORM_MONGO_URL` is mandatory.

## Safe Failure Classes

- `schema_state_missing`
- `schema_version_incompatible`
- `schema_manifest_mismatch`
- `index_missing`
- `index_definition_mismatch`
- `storage_dependency_unavailable`
- `storage_bootstrap_conflict`

Failures may include collection name, index name, expected schema version, and manifest fingerprint. They MUST NOT include connection strings, credentials, arbitrary documents, or raw driver messages.

## Compose Ordering

```text
mongo healthy -> mongo-init complete -> storage-bootstrap complete -> app start
```

The application container remains verification-only even though the bootstrap service uses the same image.
