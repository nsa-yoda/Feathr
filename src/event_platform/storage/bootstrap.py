"""Versioned Mongo collection and index bootstrap boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import CollectionInvalid, DuplicateKeyError, OperationFailure, PyMongoError

from event_platform.storage.mongo import REQUIRED_INDEXES, IndexDefinition

SCHEMA_VERSION = 1
MINIMUM_COMPATIBLE_SCHEMA_VERSION = 1
SCHEMA_DOCUMENT_ID = "event_platform_storage"


@dataclass(frozen=True, slots=True)
class StorageCollections:
    """Physical collection names governed by the storage manifest."""

    events: str = "events"
    checkpoints: str = "search_projection_checkpoints"
    rebuilds: str = "search_rebuilds"
    rebuild_leases: str = "search_rebuild_leases"
    idempotency: str = "event_idempotency"
    projection_leases: str = "search_projection_leases"
    schema: str = "storage_schema"


@dataclass(frozen=True, slots=True)
class StorageManifest:
    schema_version: int
    minimum_compatible_version: int
    indexes: Mapping[str, tuple[IndexDefinition, ...]]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class StorageVerification:
    schema_version: int
    manifest_fingerprint: str
    verified_indexes: int


class StorageSchemaError(RuntimeError):
    """A bounded schema/bootstrap failure safe for structured diagnostics."""

    def __init__(
        self,
        classification: str,
        *,
        collection: str | None = None,
        index: str | None = None,
    ) -> None:
        super().__init__(f"Storage schema operation failed: {classification}")
        self.classification = classification
        self.collection = collection
        self.index = index


class _IndexCursor(Protocol):
    async def to_list(self, length: int | None = None) -> list[Mapping[str, object]]: ...


class _Collection(Protocol):
    async def create_indexes(self, models: list[IndexModel]) -> list[str]: ...

    async def list_indexes(self) -> _IndexCursor: ...

    async def find_one(self, query: Mapping[str, object]) -> Mapping[str, object] | None: ...

    async def update_one(
        self,
        query: Mapping[str, object],
        update: Mapping[str, Mapping[str, object]],
        *,
        upsert: bool,
    ) -> object: ...


class StorageDatabase(Protocol):
    def __getitem__(self, name: str) -> _Collection: ...

    async def list_collection_names(self) -> list[str]: ...

    async def create_collection(self, name: str) -> object: ...


_CHECKPOINT_INDEXES = (
    IndexDefinition(
        "uq_search_projection_checkpoints_projector",
        (("projector", ASCENDING),),
        unique=True,
    ),
)
_REBUILD_INDEXES = (
    IndexDefinition("uq_search_rebuilds_rebuild_id", (("rebuild_id", ASCENDING),), unique=True),
    IndexDefinition("ix_search_rebuilds_started_at", (("started_at", DESCENDING),)),
)
_BUILTIN_ID_INDEX = (IndexDefinition("_id_", (("_id", ASCENDING),)),)
_IDEMPOTENCY_INDEXES = (
    _BUILTIN_ID_INDEX[0],
    IndexDefinition(
        "ttl_event_idempotency_created_at",
        (("created_at", ASCENDING),),
        expire_after_seconds=2_592_000,
    ),
)
_PROJECTION_LEASE_INDEXES = _BUILTIN_ID_INDEX


def storage_manifest(collections: StorageCollections | None = None) -> StorageManifest:
    names = collections or StorageCollections()
    indexes: dict[str, tuple[IndexDefinition, ...]] = {
        names.events: REQUIRED_INDEXES,
        names.checkpoints: _CHECKPOINT_INDEXES,
        names.rebuilds: _REBUILD_INDEXES,
        names.rebuild_leases: _BUILTIN_ID_INDEX,
        names.idempotency: _IDEMPOTENCY_INDEXES,
        names.projection_leases: _PROJECTION_LEASE_INDEXES,
        names.schema: _BUILTIN_ID_INDEX,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "minimum_compatible_version": MINIMUM_COMPATIBLE_SCHEMA_VERSION,
        "collections": [
            {
                "name": collection,
                "indexes": [
                    {
                        "name": index.name,
                        "keys": list(index.keys),
                        "unique": index.unique,
                        "expire_after_seconds": index.expire_after_seconds,
                    }
                    for index in definitions
                ],
            }
            for collection, definitions in indexes.items()
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return StorageManifest(
        schema_version=SCHEMA_VERSION,
        minimum_compatible_version=MINIMUM_COMPATIBLE_SCHEMA_VERSION,
        indexes=indexes,
        fingerprint=fingerprint,
    )


async def bootstrap_storage(
    database: StorageDatabase,
    *,
    collections: StorageCollections | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> StorageVerification:
    """Create additive schema version 1 and verify the resulting live metadata."""

    names = collections or StorageCollections()
    manifest = storage_manifest(names)
    try:
        existing = set(await database.list_collection_names())
        for collection_name in manifest.indexes:
            if collection_name in existing:
                continue
            try:
                await database.create_collection(collection_name)
            except CollectionInvalid:
                pass
        for collection_name, definitions in manifest.indexes.items():
            custom = [definition for definition in definitions if definition.name != "_id_"]
            if custom:
                await database[collection_name].create_indexes(_index_models(custom))
        await database[names.schema].update_one(
            {"_id": SCHEMA_DOCUMENT_ID},
            {
                "$setOnInsert": {
                    "schema_version": manifest.schema_version,
                    "manifest_fingerprint": manifest.fingerprint,
                    "applied_at": _utc(clock()),
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        pass
    except (CollectionInvalid, OperationFailure):
        raise StorageSchemaError("storage_bootstrap_conflict") from None
    except PyMongoError:
        raise StorageSchemaError("storage_dependency_unavailable") from None
    return await verify_storage(database, collections=names)


async def verify_storage(
    database: StorageDatabase,
    *,
    collections: StorageCollections | None = None,
) -> StorageVerification:
    """Read and validate schema compatibility without mutating MongoDB."""

    names = collections or StorageCollections()
    manifest = storage_manifest(names)
    try:
        state = await database[names.schema].find_one({"_id": SCHEMA_DOCUMENT_ID})
        if state is None:
            raise StorageSchemaError("schema_state_missing", collection=names.schema)
        version = state.get("schema_version")
        if not isinstance(version, int) or not (
            manifest.minimum_compatible_version <= version <= manifest.schema_version
        ):
            raise StorageSchemaError("schema_version_incompatible", collection=names.schema)
        if state.get("manifest_fingerprint") != manifest.fingerprint:
            raise StorageSchemaError("schema_manifest_mismatch", collection=names.schema)

        existing_collections = set(await database.list_collection_names())
        verified = 0
        for collection_name, definitions in manifest.indexes.items():
            if collection_name not in existing_collections:
                raise StorageSchemaError(
                    "index_missing",
                    collection=collection_name,
                    index=definitions[0].name,
                )
            cursor = await database[collection_name].list_indexes()
            observed = {
                str(document.get("name")): document
                for document in await cursor.to_list(length=None)
            }
            for definition in definitions:
                document = observed.get(definition.name)
                if document is None:
                    raise StorageSchemaError(
                        "index_missing", collection=collection_name, index=definition.name
                    )
                if not _index_matches(document, definition):
                    raise StorageSchemaError(
                        "index_definition_mismatch",
                        collection=collection_name,
                        index=definition.name,
                    )
                verified += 1
    except StorageSchemaError:
        raise
    except PyMongoError:
        raise StorageSchemaError("storage_dependency_unavailable") from None
    return StorageVerification(
        schema_version=manifest.schema_version,
        manifest_fingerprint=manifest.fingerprint,
        verified_indexes=verified,
    )


def _index_models(definitions: list[IndexDefinition]) -> list[IndexModel]:
    return [
        IndexModel(
            list(index.keys),
            name=index.name,
            unique=index.unique,
            **(
                {"expireAfterSeconds": index.expire_after_seconds}
                if index.expire_after_seconds is not None
                else {}
            ),
        )
        for index in definitions
    ]


def _index_matches(document: Mapping[str, object], expected: IndexDefinition) -> bool:
    raw_keys = document.get("key")
    if not isinstance(raw_keys, Mapping):
        return False
    keys = tuple((str(key), cast(int, direction)) for key, direction in raw_keys.items())
    return (
        keys == expected.keys
        and bool(document.get("unique", False)) is expected.unique
        and (
            expected.expire_after_seconds is None
            or document.get("expireAfterSeconds") == expected.expire_after_seconds
        )
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("bootstrap clock must return an aware datetime")
    return value.astimezone(UTC)
