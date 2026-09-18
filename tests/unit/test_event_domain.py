"""Pure contract tests for validated and canonical events."""

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from event_platform.domain.events import (
    MAX_METADATA_BYTES,
    MAX_METADATA_DEPTH,
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_KEYS,
    MAX_METADATA_LIST_LENGTH,
    MAX_METADATA_NUMBER_ABS,
    MAX_METADATA_STRING_LENGTH,
    MAX_SOURCE_URL_LENGTH,
    CanonicalEvent,
    EventInput,
    canonical_payload,
    metadata_key_count,
    payload_hash,
)

pytestmark = pytest.mark.unit


def valid_payload() -> dict[str, object]:
    return {
        "event_type": "pageview",
        "timestamp": "2026-01-02T03:04:05-05:00",
        "user_id": "user-123",
        "source_url": "https://example.test/path?q=one",
        "metadata": {"browser": "Safari", "count": 2, "tags": ["new", "web"]},
    }


def nested_metadata(depth: int) -> dict[str, object]:
    value: object = "leaf"
    for _ in range(depth - 1):
        value = {"nested": value}
    return value  # type: ignore[return-value]


def test_valid_input_normalizes_timestamp_to_utc_and_preserves_json_meaning() -> None:
    event = EventInput.model_validate(valid_payload())

    assert event.timestamp == datetime(2026, 1, 2, 8, 4, 5, tzinfo=UTC)
    assert str(event.source_url) == "https://example.test/path?q=one"
    assert event.metadata["tags"] == ["new", "web"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_type", ""),
        ("event_type", "x" * 129),
        ("user_id", ""),
        ("user_id", "x" * 257),
        ("source_url", "ftp://example.test/file"),
    ],
)
def test_scalar_boundaries_are_rejected(field: str, value: str) -> None:
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        EventInput.model_validate(payload)


def test_source_url_length_boundary_is_enforced() -> None:
    prefix = "https://example.test/"
    at_limit = valid_payload()
    at_limit["source_url"] = prefix + "x" * (MAX_SOURCE_URL_LENGTH - len(prefix))
    EventInput.model_validate(at_limit)

    over_limit = valid_payload()
    over_limit["source_url"] = prefix + "x" * (MAX_SOURCE_URL_LENGTH - len(prefix) + 1)
    with pytest.raises(ValidationError):
        EventInput.model_validate(over_limit)


def test_exact_scalar_and_collection_boundaries_are_accepted() -> None:
    payload = valid_payload()
    payload["metadata"] = {
        "k" * MAX_METADATA_KEY_LENGTH: "x" * MAX_METADATA_STRING_LENGTH,
        "items": list(range(MAX_METADATA_LIST_LENGTH)),
    }

    event = EventInput.model_validate(payload)

    assert len(next(iter(event.metadata))) == MAX_METADATA_KEY_LENGTH
    assert len(event.metadata["items"]) == MAX_METADATA_LIST_LENGTH  # type: ignore[arg-type]


def test_naive_and_over_future_timestamps_are_rejected() -> None:
    naive = valid_payload()
    naive["timestamp"] = "2026-01-02T03:04:05"
    with pytest.raises(ValidationError):
        EventInput.model_validate(naive)

    future = valid_payload()
    future["timestamp"] = (datetime.now(UTC) + timedelta(minutes=6)).isoformat()
    with pytest.raises(ValidationError):
        EventInput.model_validate(future)


def test_control_characters_and_raw_server_values_are_rejected_safely() -> None:
    for field in ("event_type", "user_id"):
        payload = valid_payload()
        payload[field] = "safe\nSENTINEL"
        with pytest.raises(ValidationError, match="control characters"):
            EventInput.model_validate(payload)

    payload = valid_payload()
    payload["idempotency_key"] = "SENTINEL_RAW_KEY"
    with pytest.raises(ValidationError) as error:
        EventInput.model_validate(payload)
    assert "SENTINEL_RAW_KEY" not in str(error.value)


def test_timestamp_at_future_boundary_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    import event_platform.domain.events as event_domain

    fixed_now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    monkeypatch.setattr(event_domain, "_utc_now", lambda: fixed_now)
    payload = valid_payload()
    payload["timestamp"] = (fixed_now + timedelta(minutes=5)).isoformat()

    event = EventInput.model_validate(payload)

    assert event.timestamp == fixed_now + timedelta(minutes=5)


def test_server_fields_are_rejected_from_client_input() -> None:
    payload = valid_payload()
    payload["event_id"] = str(uuid4())

    with pytest.raises(ValidationError):
        EventInput.model_validate(payload)


def test_metadata_depth_and_key_count_boundaries() -> None:
    at_depth = valid_payload()
    at_depth["metadata"] = nested_metadata(MAX_METADATA_DEPTH)
    EventInput.model_validate(at_depth)

    too_deep = valid_payload()
    too_deep["metadata"] = nested_metadata(MAX_METADATA_DEPTH + 1)
    with pytest.raises(ValidationError, match="metadata_depth_exceeded"):
        EventInput.model_validate(too_deep)

    at_keys = valid_payload()
    at_keys["metadata"] = {f"key-{index}": index for index in range(MAX_METADATA_KEYS)}
    assert metadata_key_count(EventInput.model_validate(at_keys).metadata) == MAX_METADATA_KEYS

    too_many_keys = valid_payload()
    too_many_keys["metadata"] = {f"key-{index}": index for index in range(MAX_METADATA_KEYS + 1)}
    with pytest.raises(ValidationError, match="metadata_key_count_exceeded"):
        EventInput.model_validate(too_many_keys)


def test_metadata_scalar_and_collection_limits() -> None:
    long_key = valid_payload()
    long_key["metadata"] = {"k" * (MAX_METADATA_KEY_LENGTH + 1): "ok"}
    with pytest.raises(ValidationError, match="metadata_key_length_exceeded"):
        EventInput.model_validate(long_key)

    long_string = valid_payload()
    long_string["metadata"] = {"value": "x" * (MAX_METADATA_STRING_LENGTH + 1)}
    with pytest.raises(ValidationError, match="metadata_string_length_exceeded"):
        EventInput.model_validate(long_string)

    long_list = valid_payload()
    long_list["metadata"] = {"values": list(range(MAX_METADATA_LIST_LENGTH + 1))}
    with pytest.raises(ValidationError, match="metadata_list_length_exceeded"):
        EventInput.model_validate(long_list)


def test_metadata_serialized_size_and_non_finite_numbers_are_rejected() -> None:
    at_limit = valid_payload()
    at_limit["metadata"] = {
        **{f"key-{index}": "x" * 512 for index in range(31)},
        "last": "x" * 139,
    }
    assert (
        len(json.dumps(at_limit["metadata"], ensure_ascii=False, separators=(",", ":")))
        == MAX_METADATA_BYTES
    )
    EventInput.model_validate(at_limit)

    oversized = valid_payload()
    oversized["metadata"] = {f"key-{index}": "x" * 512 for index in range(64)}
    with pytest.raises(ValidationError, match="metadata_serialized_size_exceeded"):
        EventInput.model_validate(oversized)

    non_finite = valid_payload()
    for value in (float("nan"), float("inf"), float("-inf")):
        non_finite["metadata"] = {"value": value}
        with pytest.raises(ValidationError, match="metadata_number_not_finite"):
            EventInput.model_validate(non_finite)

    at_number_limit = valid_payload()
    at_number_limit["metadata"] = {
        "positive": MAX_METADATA_NUMBER_ABS,
        "negative": -MAX_METADATA_NUMBER_ABS,
    }
    EventInput.model_validate(at_number_limit)

    over_number_limit = valid_payload()
    over_number_limit["metadata"] = {"value": MAX_METADATA_NUMBER_ABS + 1}
    with pytest.raises(ValidationError, match="metadata_number_out_of_range"):
        EventInput.model_validate(over_number_limit)

    with pytest.raises(ValidationError):
        EventInput.model_validate({**valid_payload(), "metadata": ["not", "an", "object"]})

    assert MAX_METADATA_BYTES == 16 * 1024


def test_tuple_metadata_is_rejected_before_pydantic_coercion() -> None:
    payload = valid_payload()
    payload["metadata"] = {"values": ("tuple", "must stay invalid")}

    with pytest.raises(ValidationError, match="metadata_value_unsupported"):
        EventInput.model_validate(payload)


def test_unicode_is_preserved_and_validation_errors_do_not_echo_metadata() -> None:
    payload = valid_payload()
    payload["metadata"] = {"message": "こんにちは 🌍"}
    event = EventInput.model_validate(payload)
    assert event.metadata["message"] == "こんにちは 🌍"

    secret = "SENTINEL_PRIVATE_METADATA"
    invalid = valid_payload()
    invalid["metadata"] = {"message": secret * 100}
    with pytest.raises(ValidationError) as error:
        EventInput.model_validate(invalid)
    assert secret not in str(error.value)


def test_payload_hash_is_stable_for_key_order_and_changes_for_values() -> None:
    first = EventInput.model_validate(valid_payload())
    reordered = valid_payload()
    reordered["metadata"] = {"tags": ["new", "web"], "count": 2, "browser": "Safari"}
    second = EventInput.model_validate(reordered)

    assert canonical_payload(first) == canonical_payload(second)
    assert payload_hash(first) == payload_hash(second)

    changed = valid_payload()
    changed["metadata"] = {"browser": "Chrome"}
    assert payload_hash(first) != payload_hash(EventInput.model_validate(changed))


def test_payload_hash_is_stable_across_repeated_construction() -> None:
    hashes = set()
    for iteration in range(100):
        payload = valid_payload()
        metadata = {"browser": "Safari", "count": 2, "tags": ["new", "web"]}
        if iteration % 2:
            metadata = dict(reversed(list(metadata.items())))
        payload["metadata"] = metadata
        hashes.add(payload_hash(EventInput.model_validate(payload)))

    assert len(hashes) == 1


def test_canonical_event_assigns_server_fields_and_hashes_idempotency_key() -> None:
    input_event = EventInput.model_validate(valid_payload())
    event_id = uuid4()
    ingested_at = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)

    event = CanonicalEvent.from_input(
        input_event,
        event_id=event_id,
        ingested_at=ingested_at,
        idempotency_key="SENTINEL_RAW_KEY",
    )

    assert event.event_id == event_id
    assert event.ingested_at == ingested_at
    assert event.schema_version == 1
    assert len(event.payload_hash) == 64
    assert len(event.idempotency_key_hash or "") == 64
    assert event.payload_hash == hashlib.sha256(canonical_payload(input_event).encode()).hexdigest()
    assert event.idempotency_key_hash == hashlib.sha256(b"SENTINEL_RAW_KEY").hexdigest()
    assert "SENTINEL_RAW_KEY" not in repr(event)
    assert "SENTINEL_RAW_KEY" not in str(event.model_dump())


def test_canonical_event_is_immutable_and_server_fields_do_not_change_payload_hash() -> None:
    input_event = EventInput.model_validate(valid_payload())
    first = CanonicalEvent.from_input(
        input_event,
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
        ingested_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
    )
    second = CanonicalEvent.from_input(
        input_event,
        event_id=UUID("00000000-0000-0000-0000-000000000002"),
        ingested_at=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )

    assert first.payload_hash == second.payload_hash
    with pytest.raises(ValidationError):
        first.event_type = "changed"  # type: ignore[misc]

    with pytest.raises(TypeError):
        first.metadata["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        first.metadata["tags"].append("changed")  # type: ignore[union-attr]

    direct_input = first.model_dump()
    direct_input["timestamp"] = datetime(2026, 1, 2, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    with pytest.raises(ValidationError, match="timestamp must be normalized to UTC"):
        CanonicalEvent.model_validate(direct_input)

    direct_input["timestamp"] = first.timestamp
    direct_input["ingested_at"] = datetime(2026, 1, 2, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    with pytest.raises(ValidationError, match="ingested_at must be normalized to UTC"):
        CanonicalEvent.model_validate(direct_input)


@pytest.mark.parametrize(
    "server_field",
    ["event_id", "ingested_at", "schema_version", "payload_hash", "idempotency_key_hash"],
)
def test_all_server_owned_input_fields_are_rejected(server_field: str) -> None:
    payload = valid_payload()
    payload[server_field] = "SENTINEL_SERVER_FIELD"

    with pytest.raises(ValidationError, match="server_owned_field_not_allowed"):
        EventInput.model_validate(payload)


def test_canonical_json_is_compact_utf8_and_recursively_sorted() -> None:
    payload = valid_payload()
    payload["metadata"] = {"z": {"b": "é", "a": "α"}, "a": 1}
    event = EventInput.model_validate(payload)
    canonical = canonical_payload(event)

    assert " " not in canonical
    assert "\\u00e9" not in canonical
    assert canonical.index('"a":1') < canonical.index('"z":')
    assert json.loads(canonical)["metadata"]["z"] == {"a": "α", "b": "é"}
