from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.search.mapping import (
    INDEX_MAPPING,
    index_name,
    metadata_text,
    project_search_document,
)

pytestmark = pytest.mark.unit


def event() -> CanonicalEvent:
    value = EventInput(
        event_type="view",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        user_id="u1",
        source_url="https://example.test/page",
        metadata={"Campaign": {"name": "Café", "tags": ["One", None]}, "count": 2},
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        ingested_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )


def test_mapping_is_fixed_and_versioned() -> None:
    mappings = INDEX_MAPPING["mappings"]
    assert isinstance(mappings, dict)
    assert mappings["dynamic"] is False
    properties = mappings["properties"]
    assert isinstance(properties, dict)
    assert properties["event_id"] == {"type": "keyword"}
    assert properties["event_type"] == {"type": "keyword"}
    assert properties["user_id"] == {"type": "keyword"}
    assert properties["timestamp"] == {"type": "date"}
    assert properties["metadata"] == {"type": "flattened"}
    assert properties["metadata_text"]["type"] == "text"
    settings = INDEX_MAPPING["settings"]
    assert isinstance(settings, dict)
    analyzer = settings["analysis"]["analyzer"]["metadata_text_analyzer"]
    assert analyzer["tokenizer"] == "standard"
    assert analyzer["filter"] == ["lowercase", "asciifolding"]
    assert index_name() == "events-v000001"


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"a": {"b": "Café", "list": ["One", 2, None]}}, "a b Café list One 2"),
        ({"flag": True, "off": False}, "flag true off false"),
        ({"items": [{"name": "first"}, {"name": "second"}]}, "items name first name second"),
    ],
)
def test_metadata_text_is_depth_first_and_deterministic(
    metadata: dict[str, object], expected: str
) -> None:
    assert metadata_text(metadata) == expected


def test_search_document_preserves_flattened_metadata_and_text() -> None:
    document = project_search_document(event())
    assert document["event_id"] == "00000000-0000-0000-0000-000000000001"
    assert document["metadata"] == event().metadata
    assert document["metadata_text"] == "Campaign name Café tags One count 2"
    assert set(document) == {
        "event_id",
        "event_type",
        "timestamp",
        "ingested_at",
        "user_id",
        "source_url",
        "metadata",
        "metadata_text",
        "schema_version",
    }


@pytest.mark.parametrize("prefix", ["", "bad prefix", "A"])
def test_index_name_rejects_unsafe_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        index_name(prefix)
