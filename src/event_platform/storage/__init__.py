"""Canonical storage adapter boundary."""

from event_platform.storage.bootstrap import (
    SCHEMA_VERSION,
    StorageCollections,
    StorageSchemaError,
    StorageVerification,
    bootstrap_storage,
    storage_manifest,
    verify_storage,
)
from event_platform.storage.mongo import (
    REQUIRED_INDEXES,
    EventAlreadyExists,
    EventQuery,
    MongoDependencyError,
    MongoEventStore,
)

__all__ = [
    "REQUIRED_INDEXES",
    "SCHEMA_VERSION",
    "EventAlreadyExists",
    "EventQuery",
    "MongoDependencyError",
    "MongoEventStore",
    "StorageCollections",
    "StorageSchemaError",
    "StorageVerification",
    "bootstrap_storage",
    "storage_manifest",
    "verify_storage",
]
