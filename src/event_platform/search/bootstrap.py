"""Initialize the stable search alias for a fresh local deployment."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from elastic_transport import ApiError
from elasticsearch import AsyncElasticsearch

from event_platform.search.mapping import INDEX_MAPPING, index_name


async def ensure_search_alias(client: AsyncElasticsearch, alias: str) -> str:
    """Ensure the configured alias points at a mapped physical generation.

    A new Compose volume has no Elasticsearch index yet. Creating the first
    mapped generation here keeps the projector and search API on the same
    stable alias; later online rebuilds own generation replacement.
    """

    try:
        existing = cast(
            Mapping[str, object],
            await client.indices.get_alias(name=alias, allow_no_indices=True),
        )
    except ApiError as error:
        if getattr(getattr(error, "meta", None), "status", None) != 404:
            raise
        existing = {}
    if existing:
        return sorted(existing)[0]

    physical = index_name()
    if not await client.indices.exists(index=physical):
        await client.indices.create(
            index=physical,
            settings=cast(dict[str, Any], INDEX_MAPPING["settings"]),
            mappings=cast(dict[str, Any], INDEX_MAPPING["mappings"]),
        )
    await client.indices.put_alias(index=physical, name=alias)
    return physical
