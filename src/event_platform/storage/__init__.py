"""Canonical storage adapter boundary."""

from event_platform.storage.mongo import (
    REQUIRED_INDEXES,
    EventAlreadyExists,
    EventQuery,
    MongoDependencyError,
    MongoEventStore,
)

__all__ = [
    "REQUIRED_INDEXES",
    "EventAlreadyExists",
    "EventQuery",
    "MongoDependencyError",
    "MongoEventStore",
]
