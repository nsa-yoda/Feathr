"""Official async Elasticsearch adapter for the projection boundary."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from elastic_transport import ApiError, TransportError
from elasticsearch import AsyncElasticsearch

from event_platform.observability.metrics import MetricsRegistry
from event_platform.search.projection import ProjectionError


class ElasticsearchProjectionWriter:
    def __init__(
        self,
        client: AsyncElasticsearch,
        *,
        alias: str,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not alias or len(alias) > 255:
            raise ValueError("Elasticsearch alias is invalid")
        self._client = client
        self._alias = alias
        self._metrics = metrics

    async def write(
        self,
        document_id: str,
        source: Mapping[str, object],
        *,
        target_index: str | None = None,
    ) -> None:
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            await self._client.index(index=self._alias, id=document_id, document=dict(source))
            if target_index is not None:
                await self._client.index(index=target_index, id=document_id, document=dict(source))
            outcome = "success"
        except ApiError as error:
            response_status = getattr(getattr(error, "meta", None), "status", None)
            if isinstance(response_status, int) and response_status in {408, 429}:
                raise ProjectionError("elasticsearch_unavailable", transient=True) from None
            if isinstance(response_status, int) and 400 <= response_status < 500:
                raise ProjectionError("elasticsearch_rejected") from None
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None
        except TransportError:
            raise ProjectionError("elasticsearch_unavailable", transient=True) from None
        finally:
            self._record_operation("index", outcome, started_at)

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
        started_at = time.perf_counter()
        outcome = "failure"
        try:
            response = await self._client.bulk(operations=operations)
            if bool(response.get("errors")):
                raise ProjectionError("elasticsearch_unavailable", transient=True)
            outcome = "success"
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
        finally:
            self._record_operation("bulk_index", outcome, started_at)

    def _record_operation(self, operation: str, outcome: str, started_at: float) -> None:
        if self._metrics is None:
            return
        self._metrics.observe_histogram(
            "event_platform_elasticsearch_operation_latency_seconds",
            max(0.0, time.perf_counter() - started_at),
            {"operation": operation},
        )
        self._metrics.inc(
            "event_platform_elasticsearch_operations_total",
            {"operation": operation, "outcome": outcome},
        )

    async def close(self) -> None:
        await self._client.close()


def create_client(url: str, *, request_timeout: float = 5.0) -> AsyncElasticsearch:
    if request_timeout <= 0:
        raise ValueError("request_timeout must be positive")
    return AsyncElasticsearch(hosts=[url], request_timeout=request_timeout)
