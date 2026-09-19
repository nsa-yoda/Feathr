"""Regression tests for first-deployment search alias initialization."""

from __future__ import annotations

import pytest
from elastic_transport import ApiError

from event_platform.search.bootstrap import ensure_search_alias


class FakeIndices:
    def __init__(self, aliases: dict[str, dict[str, object]] | None = None) -> None:
        self.aliases = aliases or {}
        self.created: list[dict[str, object]] = []
        self.put: list[dict[str, str]] = []

    async def get_alias(self, *, name: str, allow_no_indices: bool) -> dict[str, dict[str, object]]:
        return self.aliases.get(name, {})

    async def exists(self, *, index: str) -> bool:
        return any(item["index"] == index for item in self.created)

    async def create(self, *, index: str, settings: object, mappings: object) -> None:
        self.created.append({"index": index, "settings": settings, "mappings": mappings})

    async def put_alias(self, *, index: str, name: str) -> None:
        self.put.append({"index": index, "name": name})


class FakeClient:
    def __init__(self, indices: FakeIndices) -> None:
        self.indices = indices


class MissingAliasIndices(FakeIndices):
    async def get_alias(self, *, name: str, allow_no_indices: bool) -> dict[str, dict[str, object]]:
        raise ApiError(message="missing", meta=type("Meta", (), {"status": 404})(), body={})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_creates_mapped_generation_and_alias() -> None:
    indices = FakeIndices()

    physical = await ensure_search_alias(FakeClient(indices), "events-search")  # type: ignore[arg-type]

    assert physical == "events-v000001"
    assert indices.created[0]["index"] == "events-v000001"
    assert indices.put == [{"index": "events-v000001", "name": "events-search"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_reuses_existing_alias_without_mutation() -> None:
    indices = FakeIndices({"events-search": {"events-v000004": {}}})

    physical = await ensure_search_alias(FakeClient(indices), "events-search")  # type: ignore[arg-type]

    assert physical == "events-v000004"
    assert indices.created == []
    assert indices.put == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_treats_missing_alias_as_first_deployment() -> None:
    indices = MissingAliasIndices()

    physical = await ensure_search_alias(FakeClient(indices), "events-search")  # type: ignore[arg-type]

    assert physical == "events-v000001"
    assert indices.put == [{"index": "events-v000001", "name": "events-search"}]
