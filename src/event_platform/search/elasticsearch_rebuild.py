"""Async Elasticsearch generation and alias operations for rebuilds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
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
            refresh = getattr(self._client.indices, "refresh", None)
            if callable(refresh):
                await refresh(index=index)
            response = await self._client.count(index=index)
            value = response.get("count")
        except ApiError as error:
            raise _api_failure(error, "count_failed") from None
        except TransportError:
            raise RebuildError("elasticsearch_unavailable", transient=True) from None
        if not isinstance(value, int) or value < 0:
            raise RebuildError("count_invalid")
        return value

    def iter_event_ids(self, index: str) -> AsyncIterator[str]:
        async def ids() -> AsyncIterator[str]:
            search_after: list[object] | None = None
            try:
                # Bulk backfill intentionally uses refresh=false. Make the
                # identity read a durable visibility boundary before comparing
                # the candidate with canonical Mongo.
                refresh = getattr(self._client.indices, "refresh", None)
                if callable(refresh):
                    await refresh(index=index)
            except ApiError as error:
                raise _api_failure(error, "count_failed") from None
            except TransportError:
                raise RebuildError("elasticsearch_unavailable", transient=True) from None
            while True:
                body: dict[str, object] = {
                    "query": {"match_all": {}},
                    "_source": False,
                    "size": 500,
                    "sort": [{"event_id": "asc"}],
                }
                if search_after is not None:
                    body["search_after"] = search_after
                try:
                    response = await self._client.search(index=index, body=body)
                except ApiError as error:
                    raise _api_failure(error, "count_failed") from None
                except TransportError:
                    raise RebuildError("elasticsearch_unavailable", transient=True) from None
                hits_container = response.get("hits")
                if not isinstance(hits_container, Mapping):
                    raise RebuildError("count_invalid")
                hits = hits_container.get("hits")
                if not isinstance(hits, list):
                    raise RebuildError("count_invalid")
                if not hits:
                    return
                for hit in hits:
                    if not isinstance(hit, Mapping):
                        raise RebuildError("count_invalid")
                    source = hit.get("_source")
                    sort_values = hit.get("sort")
                    if not isinstance(source, Mapping):
                        # With _source disabled, the document ID is still safe
                        # to use as the identity reconciliation key.
                        document_id = hit.get("_id")
                    else:
                        document_id = source.get("event_id")
                    if not isinstance(document_id, str) or not isinstance(sort_values, list):
                        raise RebuildError("count_invalid")
                    yield document_id
                    search_after = list(sort_values)
                if len(hits) < 500:
                    return

        return ids()

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
