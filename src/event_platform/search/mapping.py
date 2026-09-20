"""Versioned Elasticsearch mapping and deterministic search document projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from event_platform.domain.events import CanonicalEvent, MetadataValue

INDEX_VERSION = 1
DEFAULT_INDEX_PREFIX = "events"
SEARCH_ALIAS = "events-search"

INDEX_MAPPING: dict[str, object] = {
    "settings": {
        "analysis": {
            "analyzer": {
                "metadata_text_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                }
            }
        }
    },
    "mappings": {
        "dynamic": False,
        "properties": {
            "event_id": {"type": "keyword"},
            "event_type": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "ingested_at": {"type": "date"},
            "user_id": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "metadata": {"type": "flattened"},
            "metadata_text": {"type": "text", "analyzer": "metadata_text_analyzer"},
            "schema_version": {"type": "integer"},
        },
    },
}


def index_name(prefix: str = DEFAULT_INDEX_PREFIX, *, version: int = INDEX_VERSION) -> str:
    """Return a bounded physical generation name for the stable alias."""

    if (
        not prefix
        or len(prefix) > 64
        or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in prefix)
    ):
        raise ValueError("index prefix is invalid")
    if version < 1 or version > 999_999:
        raise ValueError("index version is invalid")
    return f"{prefix}-v{version:06d}"


def metadata_text(metadata: Mapping[str, MetadataValue]) -> str:
    """Flatten metadata keys and scalar leaves in stable depth-first order."""

    parts: list[str] = []

    def visit(value: MetadataValue, path: str | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                parts.append(key)
                visit(child, key)
            return
        if isinstance(value, list):
            for child in value:
                visit(child, path)
            return
        if value is None:
            return
        if isinstance(value, bool):
            parts.append("true" if value else "false")
            return
        parts.append(str(value))

    visit(cast(MetadataValue, dict(metadata)))
    return " ".join(parts)


def project_search_document(event: CanonicalEvent) -> dict[str, object]:
    """Build the fixed-field source written to a versioned search index."""

    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "ingested_at": event.ingested_at,
        "user_id": event.user_id,
        "source_url": str(event.source_url),
        "metadata": dict(event.metadata),
        "metadata_text": metadata_text(event.metadata),
        "schema_version": event.schema_version,
    }
