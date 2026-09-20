"""Official async Elasticsearch adapter for the projection boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from elastic_transport import ApiError, TransportError
from elasticsearch import AsyncElasticsearch

from event_platform.search.projection import ProjectionError


class ElasticsearchProjectionWriter:
    def __init__(self, client: AsyncElasticsearch, *, alias: str) -> None:
        if not alias or len(alias) > 255:
            raise ValueError("Elasticsearch alias is invalid")
        self._client = client
        self._alias = alias

    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        try:
            await self._client.index(index=self._alias, id=document_id, document=dict(source))
            if target_index is not None:
                await self._client.index(index=target_index, id=document_id, document=dict(source))
        except ApiError as error:
            response_status = getattr(getattr(error, "meta", None), "status", None)
            if isinstance(response_status, int) and response_status in {408, 429}:
                raise ProjectionError("elasticsearch_unavailable", transient=True) from None
            if isinstance(response_status, int) and 400 <= response_status < 500:
                raise ProjectionError("elasticsearch_rejected") from None
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None
        except TransportError:
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None

    async def bulk_write(
        self,
        documents: Sequence[tuple[str, Mapping[str, object]]],
        *,
        target_index: str | None = None,
    ) -> None:
        if not documents or len(documents) > 1_000:
            raise ValueError("bulk projection documents are outside bounds")
        operations: list[dict[str, object]] = []
        for document_id, source in documents:
            operations.extend(
                [
                    {"index": {"_index": self._alias, "_id": document_id}},
                    dict(source),
                ]
            )
        if target_index is not None:
            for document_id, source in documents:
                operations.extend(
                    [
                        {"index": {"_index": target_index, "_id": document_id}},
                        dict(source),
                    ]
                )
        try:
            response = await self._client.bulk(operations=operations)
            if bool(response.get("errors")):
                raise ProjectionError("elasticsearch_unavailable", transient=True)
        except ProjectionError:
            raise
        except ApiError as error:
            response_status = getattr(getattr(error, "meta", None), "status", None)
            if (
                isinstance(response_status, int)
                and 400 <= response_status < 500
                and response_status != 429
            ):
                raise ProjectionError("elasticsearch_rejected") from None
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None
        except TransportError:
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None

    async def close(self) -> None:
        await self._client.close()


def create_client(url: str, *, request_timeout: float = 5.0) -> AsyncElasticsearch:
    if request_timeout <= 0:
        raise ValueError("request_timeout must be positive")
    return AsyncElasticsearch(hosts=[url], request_timeout=request_timeout)
