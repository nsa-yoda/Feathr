"""Async Elasticsearch generation and alias operations for rebuilds."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from elastic_transport import ApiError, TransportError
from elasticsearch import AsyncElasticsearch

from event_platform.search.rebuild import RebuildError, RebuildSearchPort


class ElasticsearchRebuildAdapter(RebuildSearchPort):
    def __init__(self, client: AsyncElasticsearch) -> None:
        self._client = client

    async def resolve_alias(self, alias: str) -> str | None:
        try:
            response = await self._client.indices.get_alias(name=alias, allow_no_indices=True)
        except ApiError as error:
            if getattr(getattr(error, "meta", None), "status", None) == 404:
                return None
            raise RebuildError("elasticsearch_unavailable", transient=True) from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None
        names = sorted(response)
        return names[0] if names else None

    async def create_index(self, index: str, definition: Mapping[str, object]) -> None:
        try:
            await self._client.indices.create(
                index=index,
                settings=cast(Mapping[str, Any] | None, definition.get("settings")),
                mappings=cast(Mapping[str, Any] | None, definition.get("mappings")),
            )
        except ApiError as error:
            raise _api_failure(error, "index_create_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None

    async def bulk_index(self, index: str, documents: Sequence[Mapping[str, object]]) -> int:
        operations: list[Mapping[str, object]] = []
        for document in documents:
            event_id = document.get("event_id")
            if not isinstance(event_id, str):
                raise RebuildError("bulk_document_invalid")
            operations.extend(({"index": {"_index": index, "_id": event_id}}, document))
        try:
            response = await self._client.bulk(operations=operations, refresh=False)
        except ApiError as error:
            raise _api_failure(error, "bulk_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None
        if response.get("errors"):
            raise RebuildError("bulk_rejected")
        return len(documents)

    async def count(self, index: str) -> int:
        try:
            response = await self._client.count(index=index)
            value = response.get("count")
        except ApiError as error:
            raise _api_failure(error, "count_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None
        if not isinstance(value, int) or value < 0:
            raise RebuildError("count_invalid")
        return value

    async def swap_alias(self, alias: str, old_index: str | None, new_index: str) -> None:
        actions: list[Mapping[str, object]] = []
        if old_index is not None:
            actions.append({"remove": {"index": old_index, "alias": alias}})
        actions.append({"add": {"index": new_index, "alias": alias}})
        try:
            await self._client.indices.update_aliases(actions=actions)
        except ApiError as error:
            raise _api_failure(error, "alias_swap_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None

    async def delete_index(self, index: str) -> None:
        try:
            await self._client.indices.delete(index=index, ignore_unavailable=True)
        except ApiError as error:
            raise _api_failure(error, "index_cleanup_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None

    async def close(self) -> None:
        await self._client.close()


def _api_failure(error: ApiError, permanent_code: str) -> RebuildError:
    status = getattr(getattr(error, "meta", None), "status", None)
    if isinstance(status, int) and status in {408, 425, 429, 500, 502, 503, 504}:
        return RebuildError("elasticsearch_unavailable", transient=True)
    return RebuildError(permanent_code)
