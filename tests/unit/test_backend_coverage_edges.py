"""Focused backend edge coverage for dependency and boundary adapters."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from elastic_transport import ApiError, TransportError
from pymongo.errors import DuplicateKeyError, PyMongoError
from redis.exceptions import RedisError

from event_platform import cli
from event_platform.api.middleware.production_auth import ProductionAuthMiddleware
from event_platform.cache.realtime import (
    CacheUnavailable,
    RealtimeStatsResponse,
    RealtimeStatsResultLimit,
    RealtimeStatsService,
    RedisCache,
    build_realtime_pipeline,
    cache_key,
)
from event_platform.core.logging import (
    JsonAccessLogFormatter,
    JsonLogFormatter,
    configure_logging,
)
from event_platform.core.settings import ServiceSettings, SettingsStartupError
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.rate_limit.identity import normalize_client_identity
from event_platform.search.elasticsearch import ElasticsearchProjectionWriter, create_client
from event_platform.search.elasticsearch_rebuild import ElasticsearchRebuildAdapter
from event_platform.search.projection import (
    ChangeStreamEvent,
    ProjectionCheckpoint,
    ProjectionError,
    SearchProjector,
    _copy_json,
)
from event_platform.search.projection import (
    RetryPolicy as ProjectionRetryPolicy,
)
from event_platform.search.rebuild import (
    RebuildError,
    RebuildPhase,
    RebuildRecord,
    SearchRebuilder,
    _next_prefix,
    _next_version,
)
from event_platform.search.rebuild import (
    RetryPolicy as RebuildRetryPolicy,
)
from event_platform.search.search import (
    ElasticsearchSearchService,
    SearchCursorError,
    SearchDependencyError,
    SearchQuery,
    decode_search_cursor,
    encode_search_cursor,
)
from event_platform.storage.bootstrap import StorageSchemaError, StorageVerification
from event_platform.storage.checkpoints import (
    CheckpointDependencyError,
    MongoProjectionCheckpointStore,
)
from event_platform.storage.idempotency import (
    IdempotencyRegistryError,
    InMemoryIdempotencyRegistry,
    MongoIdempotencyRegistry,
    registry_id,
)
from event_platform.storage.rebuilds import MongoRebuildStore, RebuildStorageError

pytestmark = pytest.mark.unit


def api_error(status: int) -> ApiError:
    meta = type("Meta", (), {"status": status})()
    return ApiError(message="dependency detail", meta=meta, body={})


class FakeIndices:
    def __init__(self) -> None:
        self.alias_result: Mapping[str, object] = {}
        self.alias_error: Exception | None = None
        self.create_error: Exception | None = None
        self.update_error: Exception | None = None
        self.delete_error: Exception | None = None
        self.calls: list[tuple[str, object]] = []

    async def get_alias(self, **kwargs: object) -> Mapping[str, object]:
        self.calls.append(("get_alias", kwargs))
        if self.alias_error:
            raise self.alias_error
        return self.alias_result

    async def create(self, **kwargs: object) -> None:
        self.calls.append(("create", kwargs))
        if self.create_error:
            raise self.create_error

    async def update_aliases(self, **kwargs: object) -> None:
        self.calls.append(("update_aliases", kwargs))
        if self.update_error:
            raise self.update_error

    async def delete(self, **kwargs: object) -> None:
        self.calls.append(("delete", kwargs))
        if self.delete_error:
            raise self.delete_error


class FakeElasticsearchClient:
    def __init__(self) -> None:
        self.indices = FakeIndices()
        self.bulk_response: Mapping[str, object] = {"errors": False}
        self.bulk_error: Exception | None = None
        self.count_response: Mapping[str, object] = {"count": 2}
        self.count_error: Exception | None = None
        self.closed = False

    async def bulk(self, **kwargs: object) -> Mapping[str, object]:
        self.bulk_operations = kwargs["operations"]
        if self.bulk_error:
            raise self.bulk_error
        return self.bulk_response

    async def count(self, **kwargs: object) -> Mapping[str, object]:
        self.count_index = kwargs["index"]
        if self.count_error:
            raise self.count_error
        return self.count_response

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_elasticsearch_rebuild_adapter_success_paths() -> None:
    client = FakeElasticsearchClient()
    client.indices.alias_result = {"events-v2": {}, "events-v1": {}}
    adapter = ElasticsearchRebuildAdapter(client)  # type: ignore[arg-type]

    assert await adapter.resolve_alias("events-search") == "events-v1"
    client.indices.alias_result = {}
    assert await adapter.resolve_alias("events-search") is None
    await adapter.create_index(
        "events-v2", {"settings": {"number_of_shards": 1}, "mappings": {"properties": {}}}
    )
    assert (
        await adapter.bulk_index(
            "events-v2", [{"event_id": "one", "value": 1}, {"event_id": "two"}]
        )
        == 2
    )
    assert len(client.bulk_operations) == 4  # type: ignore[arg-type]
    assert await adapter.count("events-v2") == 2
    await adapter.swap_alias("events-search", "events-v1", "events-v2")
    await adapter.delete_index("events-v1")
    await adapter.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_elasticsearch_rebuild_adapter_classifies_dependency_and_payload_failures() -> None:
    client = FakeElasticsearchClient()
    adapter = ElasticsearchRebuildAdapter(client)  # type: ignore[arg-type]

    client.indices.alias_error = api_error(404)
    assert await adapter.resolve_alias("events-search") is None
    client.indices.alias_error = api_error(400)
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.resolve_alias("events-search")
    client.indices.alias_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.resolve_alias("events-search")

    client.indices.create_error = api_error(400)
    with pytest.raises(RebuildError, match="index_create_failed"):
        await adapter.create_index("events-v2", {})
    client.indices.create_error = api_error(503)
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.create_index("events-v2", {})
    client.indices.create_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.create_index("events-v2", {})

    with pytest.raises(RebuildError, match="bulk_document_invalid"):
        await adapter.bulk_index("events-v2", [{"value": "missing id"}])
    client.bulk_response = {"errors": True}
    with pytest.raises(RebuildError, match="bulk_rejected"):
        await adapter.bulk_index("events-v2", [{"event_id": "one"}])
    client.bulk_response = {"errors": False}
    client.bulk_error = api_error(400)
    with pytest.raises(RebuildError, match="bulk_failed"):
        await adapter.bulk_index("events-v2", [{"event_id": "one"}])
    client.bulk_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.bulk_index("events-v2", [{"event_id": "one"}])
    client.bulk_error = None

    client.count_response = {"count": -1}
    with pytest.raises(RebuildError, match="count_invalid"):
        await adapter.count("events-v2")
    client.count_response = {"count": "2"}
    with pytest.raises(RebuildError, match="count_invalid"):
        await adapter.count("events-v2")
    client.count_error = api_error(400)
    with pytest.raises(RebuildError, match="count_failed"):
        await adapter.count("events-v2")
    client.count_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.count("events-v2")
    client.count_error = None
    client.indices.update_error = api_error(400)
    with pytest.raises(RebuildError, match="alias_swap_failed"):
        await adapter.swap_alias("events-search", None, "events-v2")
    client.indices.update_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.swap_alias("events-search", None, "events-v2")
    client.indices.update_error = None
    client.indices.delete_error = api_error(400)
    with pytest.raises(RebuildError, match="index_cleanup_failed"):
        await adapter.delete_index("events-v2")
    client.indices.delete_error = TransportError("down", ())
    with pytest.raises(RebuildError, match="elasticsearch_unavailable"):
        await adapter.delete_index("events-v2")


@pytest.mark.asyncio
async def test_elasticsearch_projection_writer_validates_and_classifies_writes() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.error: Exception | None = None
            self.closed = False

        async def index(self, **kwargs: object) -> None:
            if self.error:
                raise self.error
            self.calls.append(kwargs)

        async def close(self) -> None:
            self.closed = True

    with pytest.raises(ValueError):
        ElasticsearchProjectionWriter(Client(), alias="")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ElasticsearchProjectionWriter(Client(), alias="x" * 256)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        create_client("http://es.test", request_timeout=0)
    client = Client()
    writer = ElasticsearchProjectionWriter(client, alias="events")  # type: ignore[arg-type]
    await writer.write("id", {"event_id": "id"})
    await writer.close()
    assert client.closed is True
    assert len(client.calls) == 1
    for status, expected in (
        (408, "elasticsearch_unavailable"),
        (429, "elasticsearch_unavailable"),
        (400, "elasticsearch_rejected"),
        (500, "elasticsearch_unavailable"),
    ):
        client.error = api_error(status)
        with pytest.raises(Exception, match=expected):
            await writer.write("id", {})
    client.error = TransportError("down", ())
    with pytest.raises(Exception, match="elasticsearch_unavailable"):
        await writer.write("id", {})


class FakeRedis:
    def __init__(self) -> None:
        self.value: str | bytes | None = None
        self.error: Exception | None = None
        self.calls: list[tuple[str, object]] = []

    async def get(self, key: str) -> str | bytes | None:
        self.calls.append(("get", key))
        if self.error:
            raise self.error
        return self.value

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.calls.append(("set", (key, value, ex)))
        if self.error:
            raise self.error
        self.value = value


def test_realtime_cache_validation_and_redis_boundary() -> None:
    with pytest.raises(ValueError):
        RedisCache(FakeRedis(), key_prefix="INVALID")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RedisCache(FakeRedis(), key_prefix="x" * 65)  # type: ignore[arg-type]
    client = FakeRedis()
    cache = RedisCache(client, key_prefix="test")  # type: ignore[arg-type]

    import asyncio

    asyncio.run(cache.set("key", "value", ttl_seconds=5))
    assert asyncio.run(cache.get("key")) == "value"
    assert client.calls == [("set", ("test:key", "value", 5)), ("get", "test:key")]
    for error in (RedisError("redis"), OSError("os"), TimeoutError("timeout")):
        client.error = error
        with pytest.raises(CacheUnavailable, match="get"):
            asyncio.run(cache.get("key"))
        with pytest.raises(CacheUnavailable, match="set"):
            asyncio.run(cache.set("key", "value", ttl_seconds=5))

    with pytest.raises(ValueError):
        cache_key(5, max_event_types=0)
    with pytest.raises(ValueError):
        build_realtime_pipeline(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC), max_event_types=0
        )


@pytest.mark.parametrize(
    "documents",
    [
        [{}],
        [{"_id": "", "count": 1}],
        [{"_id": "view", "count": True}],
        [{"_id": "view", "count": 0}],
        [{"_id": "view", "count": 1}, {"_id": "view", "count": 1}],
    ],
)
def test_realtime_stats_rejects_malformed_canonical_aggregation(documents: list[object]) -> None:
    class Store:
        async def aggregate(
            self, pipeline: object, *, max_time_ms: int | None = None
        ) -> list[object]:
            del pipeline, max_time_ms
            return documents

    import asyncio

    service = RealtimeStatsService(
        store=Store(), cache=None, now=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )  # type: ignore[arg-type]
    with pytest.raises(Exception, match="decode_realtime_stats"):
        asyncio.run(service.get(window_minutes=5, request_id=UUID(int=8)))


def test_realtime_stats_bounds_and_clock_failures() -> None:
    import asyncio

    with pytest.raises(ValueError):
        RealtimeStatsService(store=object(), cache=None, ttl_seconds=0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RealtimeStatsService(store=object(), cache=None, max_event_types=0)  # type: ignore[arg-type]
    service = RealtimeStatsService(store=object(), cache=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(service.get(window_minutes=0, request_id=UUID(int=8)))
    invalid_clock = RealtimeStatsService(
        store=object(),
        cache=None,
        now=lambda: datetime(2026, 1, 1),  # type: ignore[arg-type]
    )
    with pytest.raises(Exception, match="clock_invalid"):
        asyncio.run(invalid_clock.get(window_minutes=5, request_id=UUID(int=8)))
    with pytest.raises(RealtimeStatsResultLimit):

        class Store:
            async def aggregate(
                self, pipeline: object, *, max_time_ms: int | None = None
            ) -> list[object]:
                del pipeline, max_time_ms
                return [{"_id": str(index), "count": 1} for index in range(2)]

        limited = RealtimeStatsService(
            store=Store(),
            cache=None,
            max_event_types=1,
            now=lambda: datetime(2026, 1, 1, tzinfo=UTC),  # type: ignore[arg-type]
        )
        asyncio.run(limited.get(window_minutes=5, request_id=UUID(int=8)))


def test_realtime_response_validator_rejects_inconsistent_counts_and_times() -> None:
    from datetime import datetime

    kwargs = {
        "total_events": 1,
        "by_event_type": {"view": 1},
        "generated_at": datetime(2026, 1, 1, 12, tzinfo=UTC),
        "window_start": datetime(2026, 1, 1, 11, tzinfo=UTC),
        "window_end": datetime(2026, 1, 1, 12, tzinfo=UTC),
        "request_id": UUID(int=1),
    }
    assert RealtimeStatsResponse(**kwargs).total_events == 1
    for update in (
        {"total_events": 2},
        {"by_event_type": {"view": 0}, "total_events": 0},
        {"window_start": datetime(2026, 1, 1, 13, tzinfo=UTC)},
        {"generated_at": datetime(2026, 1, 1, 11, tzinfo=UTC)},
        {"window_end": datetime(2026, 1, 1, 12)},
    ):
        with pytest.raises(ValueError):
            RealtimeStatsResponse(**{**kwargs, **update})


def test_search_cursor_rejects_malformed_payloads_and_query_bounds() -> None:
    with pytest.raises(ValueError):
        SearchQuery(q="x", start=datetime(2026, 1, 1, tzinfo=UTC), end=None)
    with pytest.raises(ValueError):
        SearchQuery(
            q="x", start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2028, 1, 1, tzinfo=UTC)
        )
    with pytest.raises(ValueError):
        SearchQuery.model_validate({"q": "x", "event_type": "bad\x7f"})
    scope = b"scope"
    for token in ("", "a", "a.b.c", "x" * 513, "not-base64."):
        with pytest.raises(SearchCursorError):
            decode_search_cursor(token, scope=scope)
    for values in ([True, "x"], [float("nan"), "x"], ["x" * 257, "x"], ["only-one"]):
        token = encode_search_cursor(list(values), scope=scope)
        with pytest.raises(SearchCursorError):
            decode_search_cursor(token, scope=scope)
    with pytest.raises(SearchCursorError):
        encode_search_cursor(["x" * 1_000], scope=scope)


def projection_event() -> CanonicalEvent:
    value = EventInput.model_validate(
        {
            "event_type": "view",
            "timestamp": "2026-01-01T12:00:00Z",
            "user_id": "user",
            "source_url": "https://example.test",
            "metadata": {"items": [1, {"nested": True}]},
        }
    )
    return CanonicalEvent.from_input(
        value,
        event_id=UUID(int=10),
        ingested_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )


class ProjectionCheckpointFake:
    def __init__(self, current: ProjectionCheckpoint | None = None) -> None:
        self.current = current
        self.error: ProjectionError | None = None
        self.saved: list[ProjectionCheckpoint] = []

    async def load(self, projector: str) -> ProjectionCheckpoint | None:
        del projector
        if self.error:
            raise self.error
        return self.current

    async def save(self, checkpoint: ProjectionCheckpoint) -> None:
        self.saved.append(checkpoint)
        self.current = checkpoint


class ProjectionWriterFake:
    async def write(
        self, document_id: str, source: Mapping[str, object], *, target_index: str | None = None
    ) -> None:
        del document_id, source, target_index


def test_projection_policy_and_constructor_bounds() -> None:
    assert _copy_json({"items": [1, {"two": 2}]}) == {"items": [1, {"two": 2}]}
    with pytest.raises(ValueError):
        ProjectionError("unsupported")
    with pytest.raises(ValueError):
        ProjectionRetryPolicy(initial_delay=-1)
    with pytest.raises(ValueError):
        ProjectionRetryPolicy(multiplier=0)
    with pytest.raises(ValueError):
        ProjectionRetryPolicy(jitter_ratio=2)
    policy = ProjectionRetryPolicy(initial_delay=2, multiplier=2, max_delay=3, jitter_ratio=0)
    assert policy.delay(2) == 3
    with pytest.raises(ValueError):
        policy.delay(0)
    checkpoint = ProjectionCheckpointFake()
    writer = ProjectionWriterFake()
    with pytest.raises(ValueError):
        SearchProjector(projector="", checkpoint=checkpoint, writer=writer)
    with pytest.raises(ValueError):
        SearchProjector(projector="p", owner="", checkpoint=checkpoint, writer=writer)
    with pytest.raises(ValueError):
        SearchProjector(projector="p", generation=-1, checkpoint=checkpoint, writer=writer)


@pytest.mark.asyncio
async def test_projection_stopped_invalid_and_target_state_paths() -> None:
    checkpoint = ProjectionCheckpointFake()
    projector = SearchProjector(projector="p", checkpoint=checkpoint, writer=ProjectionWriterFake())
    await projector.set_target_index("events-v2")
    await projector.set_target_index(None)
    with pytest.raises(ValueError):
        await projector.set_target_index("")
    with pytest.raises(ValueError):
        await projector.set_target_index("x" * 256)
    projector.stop()
    assert (await projector.start()).state == "stopped"
    with pytest.raises(ProjectionError, match="projector_stopped"):
        await projector.project_change(ChangeStreamEvent({"_data": "x"}, projection_event()))

    invalid = ProjectionCheckpointFake()
    invalid.error = ProjectionError("checkpoint_invalid")
    invalid_projector = SearchProjector(
        projector="p", checkpoint=invalid, writer=ProjectionWriterFake()
    )
    assert (await invalid_projector.start()).state == "reconciliation_required"
    dependency = ProjectionCheckpointFake()
    dependency.error = ProjectionError("checkpoint_unavailable", transient=True)
    degraded = SearchProjector(projector="p", checkpoint=dependency, writer=ProjectionWriterFake())
    assert (await degraded.start()).failure_code == "checkpoint_unavailable"
    running = SearchProjector(
        projector="p", checkpoint=ProjectionCheckpointFake(), writer=ProjectionWriterFake()
    )
    await running.start()
    with pytest.raises(ProjectionError, match="change_malformed"):
        await running.project_change(ChangeStreamEvent({}, projection_event()))


@pytest.mark.asyncio
async def test_projection_retry_limit_and_reconciliation_consumption_paths() -> None:
    projector = SearchProjector(
        projector="p", checkpoint=ProjectionCheckpointFake(), writer=ProjectionWriterFake()
    )
    await projector.start()
    with pytest.raises(ProjectionError, match="retry_exhausted"):
        await projector.retry_change(
            ChangeStreamEvent({"_data": "x"}, projection_event()), attempt=6
        )
    projector.mark_reconciliation_required()

    async def empty() -> object:
        if False:
            yield None

    assert (await projector._consume(empty())).state == "reconciliation_required"  # type: ignore[arg-type]

    stopped = SearchProjector(
        projector="p", checkpoint=ProjectionCheckpointFake(), writer=ProjectionWriterFake()
    )
    stopped.stop()
    assert (
        await stopped.run_source(type("Source", (), {"stream": lambda self, **kwargs: empty()})())
    ).state == "stopped"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_projection_inner_retry_and_run_source_dependency_exhaustion() -> None:
    class FailingWriter(ProjectionWriterFake):
        def __init__(self) -> None:
            self.calls = 0

        async def write(
            self, document_id: str, source: Mapping[str, object], *, target_index: str | None = None
        ) -> None:
            del document_id, source, target_index
            self.calls += 1
            if self.calls == 1:
                raise ProjectionError("elasticsearch_unavailable", transient=True)
            raise ProjectionError("elasticsearch_rejected")

    async def stream() -> object:
        yield ChangeStreamEvent({"_data": "x"}, projection_event())

    projector = SearchProjector(
        projector="p",
        checkpoint=ProjectionCheckpointFake(),
        writer=FailingWriter(),
        retry_policy=ProjectionRetryPolicy(
            initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2
        ),
        sleep=lambda _delay: asyncio.sleep(0),
    )
    assert (await projector.run(stream())).failure_code == "retry_exhausted"  # type: ignore[arg-type]

    class DependencySource:
        def stream(self, **kwargs: object) -> object:
            del kwargs

            async def failing() -> object:
                raise ProjectionError("dependency_unavailable", transient=True)
                yield  # pragma: no cover

            return failing()

    exhausted = SearchProjector(
        projector="p",
        checkpoint=ProjectionCheckpointFake(),
        writer=ProjectionWriterFake(),
        retry_policy=ProjectionRetryPolicy(
            initial_delay=0, max_delay=0, jitter_ratio=0, max_attempts=2
        ),
        sleep=lambda _delay: asyncio.sleep(0),
    )
    status = await exhausted.run_source(DependencySource())  # type: ignore[arg-type]
    assert status.failure_code == "retry_exhausted"


class RebuildStateFake:
    def __init__(self) -> None:
        self.saved: list[RebuildRecord] = []
        self.save_error: Exception | None = None

    async def save(self, record: RebuildRecord) -> None:
        if self.save_error:
            raise self.save_error
        self.saved.append(record)


class RebuildSearchFake:
    def __init__(self) -> None:
        self.delete_error: Exception | None = None
        self.bulk_error: Exception | None = None

    async def bulk_index(self, index: str, documents: object) -> int:
        del index, documents
        if self.bulk_error:
            raise self.bulk_error
        return 1

    async def delete_index(self, index: str) -> None:
        del index
        if self.delete_error:
            raise self.delete_error


def rebuild_source_empty() -> object:
    async def scan() -> object:
        if False:
            yield projection_event()

    return type("Source", (), {"scan": lambda self: scan()})()


def test_rebuild_helpers_and_constructor_bounds() -> None:
    assert _next_prefix("events-v000002", "alias") == "events"
    assert _next_prefix("events-vbad", "alias") == "events"
    assert _next_prefix(None, "alias") == "alias"
    assert _next_version("events-v2") == 3
    assert _next_version("events-vbad") == 1
    assert _next_version(None) == 1
    state = RebuildStateFake()
    search = RebuildSearchFake()
    with pytest.raises(ValueError):
        SearchRebuilder(state=state, search=search, source=rebuild_source_empty(), owner="")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SearchRebuilder(
            state=state, search=search, source=rebuild_source_empty(), owner="x", batch_size=0
        )  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SearchRebuilder(
            state=state,
            search=search,
            source=rebuild_source_empty(),
            owner="x",
            lease_duration=timedelta(0),
        )  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SearchRebuilder(
            state=state,
            search=search,
            source=rebuild_source_empty(),
            owner="x",
            rollback_retention=timedelta(days=-1),
        )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rebuild_retry_lease_and_cleanup_branches() -> None:
    class NoRenewState:
        async def save(self, record: RebuildRecord) -> None:
            del record

    class TransientSearch(RebuildSearchFake):
        async def bulk_index(self, index: str, documents: object) -> int:
            del index, documents
            raise RebuildError("bulk_unavailable", transient=True)

    rebuilder = SearchRebuilder(
        state=NoRenewState(),  # type: ignore[arg-type]
        search=TransientSearch(),
        source=rebuild_source_empty(),
        owner="owner",
        retry_policy=RebuildRetryPolicy(max_attempts=2, delay_seconds=0),
        sleep=lambda _delay: asyncio.sleep(0),
    )
    record = rebuild_record()
    assert await rebuilder._renew_lease(record) is True
    count, failures = await rebuilder._bulk_with_retry("target", [{"event_id": "id"}])
    assert count == 0 and failures[0].code == "bulk_unavailable"
    state = RebuildStateFake()
    search = RebuildSearchFake()
    search.delete_error = RuntimeError("cleanup")
    rebuilder = SearchRebuilder(
        state=state, search=search, source=rebuild_source_empty(), owner="owner"
    )  # type: ignore[arg-type]
    await rebuilder._record_failure(record, "target", "failure")
    assert state.saved[-1].phase == RebuildPhase.FAILED
    state.save_error = RuntimeError("state")
    await rebuilder._record_failure(record, "target", "failure")
    rebuilder._alias_swapped = True
    await rebuilder._record_failure(record, "target", "failure")


@pytest.mark.asyncio
async def test_search_service_accepts_previous_cursor_key_and_rejects_bad_responses() -> None:
    class Client:
        def __init__(self, response: object) -> None:
            self.response = response

        async def search(self, **kwargs: object) -> object:
            del kwargs
            return self.response

    with pytest.raises(ValueError):
        ElasticsearchSearchService(Client({}), alias="")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ElasticsearchSearchService(Client({}), cursor_key=b"short")  # type: ignore[arg-type]
    old = b"o" * 32
    current = b"c" * 32
    token = encode_search_cursor(
        ["timestamp", "id"],
        scope=b'{"end":null,"event_type":null,"q":"x","start":null,"user_id":null}',
        key=old,
    )
    service = ElasticsearchSearchService(
        Client({"hits": {"hits": []}}),
        cursor_key=current,
        previous_cursor_key=old,  # type: ignore[arg-type]
    )
    page = await service.search(SearchQuery(q="x", cursor=token), request_id=UUID(int=2))
    assert page.items == []
    responses = (
        {},
        {"hits": {"hits": "bad"}},
        {"hits": {"hits": ["bad"]}},
        {"hits": {"hits": [{"_source": {}, "sort": [1]}]}},
        {"hits": {"hits": [{"_source": {}, "sort": [True, 1]}]}},
    )
    for response in responses:
        with pytest.raises(SearchDependencyError):
            await ElasticsearchSearchService(Client(response)).search(
                SearchQuery(q="x"), request_id=UUID(int=3)
            )  # type: ignore[arg-type]

    class InvalidCursorClient(Client):
        async def search(self, **kwargs: object) -> object:
            del kwargs
            return {"hits": {"hits": []}}

    with pytest.raises(SearchCursorError):
        await ElasticsearchSearchService(InvalidCursorClient({}), cursor_key=current).search(
            SearchQuery(q="x", cursor="tampered"), request_id=UUID(int=4)
        )


def test_cli_dispatches_search_and_classifies_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "rebuild_main", lambda args: calls.append(list(args)) or 7)
    assert cli.main(["search", "rebuild", "--confirm"]) == 7
    assert cli.main(["search", "rebuild-status", "--rebuild-id", "abc"]) == 7
    assert calls == [["run", "--confirm"], ["status", "--rebuild-id", "abc"]]
    monkeypatch.setattr(
        cli,
        "load_settings",
        lambda: (_ for _ in ()).throw(SettingsStartupError("invalid")),
    )
    assert cli.storage_main("verify") == 2


def test_cli_rejects_missing_mongo_and_reports_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: ServiceSettings(env="test"))
    assert cli.storage_main("verify") == 2

    settings = ServiceSettings(env="test", mongo_url="mongodb://mongo.test")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)

    class Client:
        async def close(self) -> None:
            return None

        def __getitem__(self, _name: str) -> object:
            return object()

    monkeypatch.setattr(cli, "AsyncMongoClient", lambda *args, **kwargs: Client())

    async def bad_operation(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        raise StorageSchemaError("schema_state_missing")

    monkeypatch.setattr(cli, "verify_storage", bad_operation)
    assert cli.storage_main("verify") == 1

    async def bootstrap(*args: object, **kwargs: object) -> StorageVerification:
        del args, kwargs
        return StorageVerification(1, "a" * 64, 10)

    monkeypatch.setattr(cli, "bootstrap_storage", bootstrap)
    assert cli.storage_main("bootstrap") == 0

    with pytest.raises(ValueError, match="unsupported storage operation"):
        # Directly exercise the defensive branch behind the CLI parser.
        import asyncio

        asyncio.run(cli._run_storage_operation("unknown", settings))


@pytest.mark.asyncio
async def test_in_memory_idempotency_handles_expiry_and_type_boundaries() -> None:
    registry = InMemoryIdempotencyRegistry()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    args = {
        "scope": "scope",
        "key": "key",
        "operation": "operation",
        "fingerprint": "fingerprint",
        "event_id": UUID(int=1),
        "now": now,
        "replay_window": timedelta(minutes=1),
    }
    with pytest.raises(TypeError):
        await registry.reserve(**{**args, "now": "bad"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await registry.reserve(**{**args, "event_id": "bad"})  # type: ignore[arg-type]
    assert (await registry.reserve(**args)).outcome == "new"
    assert (
        await registry.reserve(
            **{**args, "now": now + timedelta(minutes=2), "event_id": UUID(int=2)}
        )
    ).outcome == "new"
    await registry.complete(scope="scope", key="key", operation="operation", event_id=UUID(int=99))
    await registry.complete(scope="scope", key="key", operation="operation", event_id=UUID(int=2))
    assert (
        await registry.reserve(
            **{**args, "now": now + timedelta(minutes=2), "event_id": UUID(int=3)}
        )
    ).outcome == "replay"

    fresh = await registry.reserve(
        **{**args, "key": "fresh-key", "event_id": UUID(int=3), "now": now}
    )
    assert fresh.reservation_token is not None
    await registry.complete(
        scope="scope",
        key="fresh-key",
        operation="operation",
        event_id=UUID(int=3),
        reservation_token="stale-token",
    )
    await registry.release(
        scope="scope",
        key="fresh-key",
        operation="operation",
        event_id=UUID(int=3),
        reservation_token="stale-token",
    )
    await registry.release(
        scope="scope",
        key="fresh-key",
        operation="operation",
        event_id=UUID(int=3),
        reservation_token=fresh.reservation_token,
    )


class IdempotencyCollection:
    def __init__(self, document: dict[str, object] | None = None) -> None:
        self.document = document
        self.error: Exception | None = None
        self.duplicate = False
        self.update_error = False

    async def find_one(self, _query: Mapping[str, object]) -> dict[str, object] | None:
        if self.error:
            raise self.error
        return self.document

    async def insert_one(self, document: dict[str, object]) -> None:
        if self.duplicate:
            raise DuplicateKeyError("duplicate", 11000)
        self.document = document

    async def update_one(self, _query: Mapping[str, object], update: Mapping[str, object]) -> None:
        if self.update_error:
            raise PyMongoError("update failed")
        values = update.get("$set")
        if isinstance(values, dict):
            self.document = {**(self.document or {}), **values}

    async def find_one_and_update(
        self,
        query: Mapping[str, object],
        update: Mapping[str, object],
        **_kwargs: object,
    ) -> dict[str, object] | None:
        if self.update_error:
            raise PyMongoError("update failed")
        document = self.document
        if document is None or any(document.get(key) != value for key, value in query.items()):
            return None
        values = update.get("$set")
        if isinstance(values, dict):
            document = {**document, **values}
        increments = update.get("$inc")
        if isinstance(increments, dict):
            document = {
                **document,
                **{
                    key: int(document.get(key, 0)) + int(value) for key, value in increments.items()
                },
            }
        self.document = document
        return document

    async def delete_one(self, _query: Mapping[str, object]) -> None:
        if self.update_error:
            raise PyMongoError("delete failed")
        self.document = None


def idem_args(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "scope": "scope",
        "key": "key",
        "operation": "operation",
        "fingerprint": "fingerprint",
        "event_id": UUID(int=1),
        "now": datetime(2026, 1, 1, tzinfo=UTC),
        "replay_window": timedelta(minutes=1),
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_mongo_idempotency_registry_reserves_replays_conflicts_and_refreshes() -> None:
    collection = IdempotencyCollection()
    registry = MongoIdempotencyRegistry(collection)  # type: ignore[arg-type]
    assert (await registry.reserve(**idem_args())).outcome == "new"
    collection.document = {**collection.document, "status": "completed"}  # type: ignore[arg-type]
    assert (await registry.reserve(**idem_args(event_id=UUID(int=2)))).outcome == "replay"
    assert (await registry.reserve(**idem_args(fingerprint="different"))).outcome == "conflict"
    collection.document = {**collection.document, "status": "reserved"}  # type: ignore[arg-type]
    assert (await registry.reserve(**idem_args(event_id=UUID(int=3)))).outcome == "in_flight"
    assert (
        await registry.reserve(
            **idem_args(event_id=UUID(int=4), now=datetime(2026, 1, 1, 1, tzinfo=UTC))
        )
    ).outcome == "new"
    await registry.complete(scope="scope", key="key", operation="operation", event_id=UUID(int=4))


@pytest.mark.asyncio
async def test_mongo_idempotency_registry_handles_duplicate_and_driver_errors() -> None:
    collection = IdempotencyCollection()
    registry = MongoIdempotencyRegistry(collection)  # type: ignore[arg-type]
    collection.duplicate = True
    collection.document = {
        "fingerprint": "fingerprint",
        "event_id": str(UUID(int=9)),
        "status": "completed",
    }
    assert (await registry.reserve(**idem_args())).event_id == UUID(int=9)
    collection.document = None
    collection.duplicate = False
    collection.error = PyMongoError("find failed")
    with pytest.raises(IdempotencyRegistryError, match="reserve_idempotency"):
        await registry.reserve(**idem_args())
    collection.error = None
    collection.document = []  # type: ignore[assignment]
    with pytest.raises(IdempotencyRegistryError, match="reserve_idempotency"):
        await registry.reserve(**idem_args())
    collection.document = {
        "fingerprint": "fingerprint",
        "event_id": str(UUID(int=1)),
        "status": "reserved",
        "created_at": datetime(2020, 1, 1, tzinfo=UTC),
    }
    collection.update_error = True
    with pytest.raises(IdempotencyRegistryError, match="reserve_idempotency"):
        await registry.reserve(**idem_args())
    collection.update_error = True
    with pytest.raises(IdempotencyRegistryError, match="complete_idempotency"):
        await registry.complete(
            scope="scope", key="key", operation="operation", event_id=UUID(int=1)
        )


@pytest.mark.asyncio
async def test_mongo_idempotency_registry_covers_owner_fenced_completion_release_and_takeover() -> (
    None
):
    collection = IdempotencyCollection(
        {
            "_id": registry_id("scope", "key", "operation"),
            "fingerprint": "fingerprint",
            "event_id": str(UUID(int=1)),
            "status": "reserved",
            "created_at": datetime(2020, 1, 1, tzinfo=UTC),
            "reservation_token": "old-token",
            "generation": 1,
        }
    )
    registry = MongoIdempotencyRegistry(collection)  # type: ignore[arg-type]

    collection.update_error = False
    refreshed = await registry.reserve(**idem_args(event_id=UUID(int=2)))
    assert refreshed.outcome == "new"
    assert refreshed.reservation_token is not None

    await registry.complete(
        scope="scope",
        key="key",
        operation="operation",
        event_id=UUID(int=2),
        reservation_token=refreshed.reservation_token,
    )
    await registry.release(
        scope="scope",
        key="key",
        operation="operation",
        event_id=UUID(int=2),
        reservation_token=refreshed.reservation_token,
    )

    collection.document = {
        "_id": registry_id("scope", "key", "operation"),
        "fingerprint": "fingerprint",
        "event_id": str(UUID(int=1)),
        "status": "reserved",
        "created_at": datetime(2020, 1, 1, tzinfo=UTC),
        "reservation_token": "old-token",
        "generation": "bad",
    }
    with pytest.raises(IdempotencyRegistryError, match="reserve_idempotency"):
        await registry.reserve(**idem_args(event_id=UUID(int=2)))


class RebuildCollection:
    def __init__(self) -> None:
        self.return_document: Mapping[str, object] | None = None
        self.document: Mapping[str, object] | None = None
        self.error: Exception | None = None
        self.replace_error: Exception | None = None
        self.update_result = type("Result", (), {"matched_count": 1, "modified_count": 1})()

    async def find_one_and_update(
        self, *_args: object, **_kwargs: object
    ) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        return self.return_document

    async def replace_one(self, *_args: object, **_kwargs: object) -> None:
        if self.replace_error:
            raise self.replace_error

    async def update_one(self, *_args: object, **_kwargs: object) -> object:
        if self.error:
            raise self.error
        return self.update_result

    async def find_one(self, *_args: object, **_kwargs: object) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        return self.document


def rebuild_record() -> RebuildRecord:
    return RebuildRecord(
        rebuild_id=UUID(int=7),
        phase=RebuildPhase.ACQUIRING,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_collection="events",
        target_index="events-v2",
        owner="owner",
        lease_expires_at=datetime(2026, 1, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_mongo_rebuild_store_handles_leases_queries_and_decode_failures() -> None:
    collection = RebuildCollection()
    record = rebuild_record()
    collection.return_document = {"rebuild_id": str(record.rebuild_id), "fencing_token": 4}
    store = MongoRebuildStore(collection)  # type: ignore[arg-type]
    assert await store.acquire(record) is True
    assert collection.return_document["fencing_token"] == 4
    collection.return_document = {"rebuild_id": "other"}
    assert await store.acquire(record) is False
    collection.error = DuplicateKeyError("duplicate", 11000)
    assert await store.acquire(record) is False
    collection.error = PyMongoError("acquire failed")
    with pytest.raises(RebuildStorageError, match="acquire_rebuild_lease"):
        await store.acquire(record)
    collection.error = None
    collection.return_document = {"rebuild_id": str(record.rebuild_id), "fencing_token": 4}
    collection.replace_error = PyMongoError("save failed")
    with pytest.raises(RebuildStorageError, match="save_rebuild"):
        await store.acquire(record)
    collection.replace_error = None
    with pytest.raises(RebuildStorageError, match="save_rebuild"):
        collection.replace_error = PyMongoError("save failed")
        await store.save(record)
    collection.replace_error = None
    collection.update_result = type("Result", (), {"matched_count": 0, "modified_count": 0})()
    assert await store.renew(record, datetime(2026, 1, 1, 2, tzinfo=UTC)) is False
    collection.update_result = type("Result", (), {"matched_count": 1, "modified_count": 0})()
    assert await store.renew(record, datetime(2026, 1, 1, 2, tzinfo=UTC)) is True
    collection.error = PyMongoError("renew failed")
    with pytest.raises(RebuildStorageError, match="renew_rebuild_lease"):
        await store.renew(record, datetime(2026, 1, 1, 2, tzinfo=UTC))
    with pytest.raises(RebuildStorageError, match="load_rebuild"):
        await store.latest()
    with pytest.raises(RebuildStorageError, match="load_rebuild"):
        await store.get(record.rebuild_id)


@pytest.mark.asyncio
async def test_mongo_rebuild_store_returns_none_and_rejects_invalid_documents() -> None:
    collection = RebuildCollection()
    store = MongoRebuildStore(collection)  # type: ignore[arg-type]
    assert await store.latest() is None
    assert await store.get(UUID(int=1)) is None
    collection.document = {"rebuild_id": "not-a-record"}
    with pytest.raises(RebuildStorageError, match="decode_rebuild"):
        await store.latest()
    with pytest.raises(RebuildStorageError, match="decode_rebuild"):
        await store.get(UUID(int=1))


def test_identity_parser_rejects_malformed_trusted_proxy_inputs() -> None:
    assert normalize_client_identity({}) == "unknown"
    assert normalize_client_identity({"client": ("not-an-ip", 1)}) == "unknown"
    base = {"client": ("192.0.2.1", 1)}
    assert (
        normalize_client_identity({**base, "headers": "bad"}, trusted_proxy_hops=1) == "192.0.2.1"
    )
    invalid_headers = [[], [b"bad"], [("x-forwarded-for", b"192.0.2.2")], [(b"x", b"y", b"z")]]
    for headers in invalid_headers:
        assert (
            normalize_client_identity({**base, "headers": headers}, trusted_proxy_hops=1)
            == "192.0.2.1"
        )
    assert (
        normalize_client_identity(
            {**base, "headers": [(b"x-forwarded-for", b"192.0.2.2, 192.0.2.1")]},
            trusted_proxy_hops=2,
        )
        == "192.0.2.1"
    )
    assert (
        normalize_client_identity(
            {**base, "headers": [(b"x-forwarded-for", b"192.0.2.2, \xff")]}, trusted_proxy_hops=1
        )
        == "192.0.2.1"
    )


class AuthSettings:
    env = "production"
    production_api_token = "t" * 32


class AuthApp:
    state = type("State", (), {"settings": AuthSettings()})()


@pytest.mark.asyncio
async def test_production_auth_allows_exempt_and_valid_requests() -> None:
    calls: list[str] = []

    async def downstream(scope: object, receive: object, send: object) -> None:
        del scope, receive, send
        calls.append("downstream")

    def receive() -> None:
        return None

    def send(_message: object) -> None:
        return None

    middleware = ProductionAuthMiddleware(downstream)
    await middleware({"type": "websocket", "path": "/protected"}, receive, send)  # type: ignore[arg-type]
    await middleware(
        {"type": "http", "path": "/health/live", "headers": [], "app": AuthApp()},
        receive,
        send,  # type: ignore[arg-type]
    )
    await middleware(
        {
            "type": "http",
            "path": "/protected",
            "headers": [(b"authorization", b"Bearer " + b"t" * 32)],
            "app": AuthApp(),
        },
        receive,
        send,  # type: ignore[arg-type]
    )
    await middleware(
        {"type": "http", "path": "/protected", "headers": [], "app": type("A", (), {})()},
        receive,
        send,  # type: ignore[arg-type]
    )
    assert calls == ["downstream"] * 4


@pytest.mark.asyncio
async def test_production_auth_rejects_malformed_and_unicode_tokens() -> None:
    messages: list[dict[str, object]] = []

    async def downstream(*_args: object) -> None:
        raise AssertionError("must not reach downstream")

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    for headers in (
        [],
        [(b"authorization", b"Basic abc")],
        [(b"authorization", b"Bearer short")],
        [(b"authorization", b"Bearer " + b"\xff" * 32)],
    ):
        await ProductionAuthMiddleware(downstream)(
            {
                "type": "http",
                "path": "/protected",
                "headers": headers,
                "state": {},
                "app": AuthApp(),
            },
            lambda: None,
            send,  # type: ignore[arg-type]
        )
    starts = [item for item in messages if item.get("type") == "http.response.start"]
    assert len(starts) == 4
    assert all(item["status"] == 401 for item in starts)


def test_json_formatters_cover_runtime_and_access_event_shapes() -> None:
    formatter = JsonLogFormatter()
    records = [
        logging.makeLogRecord({"name": "service", "msg": "plain"}),
        logging.makeLogRecord({"name": "uvicorn.error", "msg": "Application startup complete"}),
        logging.makeLogRecord({"name": "uvicorn.error", "msg": "unclassified"}),
        logging.makeLogRecord({"name": "service", "msg": "explicit", "event": "custom.event"}),
    ]
    assert json.loads(formatter.format(records[0]))["event"] == "runtime.log"
    assert json.loads(formatter.format(records[1]))["event"] == "server.startup_complete"
    assert json.loads(formatter.format(records[2]))["event"] == "server.runtime"
    assert json.loads(formatter.format(records[3]))["event"] == "custom.event"
    access = JsonAccessLogFormatter()
    rendered = json.loads(
        access.format(
            logging.makeLogRecord(
                {
                    "name": "uvicorn.access",
                    "msg": '127.0.0.1 - "GET /events/abc?q=secret HTTP/1.1" 200',
                }
            )
        )
    )
    assert rendered["event"] == "http.access"
    assert rendered["path"] == "events_detail"
    assert "secret" not in rendered["message"]
    queryless = json.loads(
        access.format(logging.makeLogRecord({"name": "uvicorn.access", "msg": "GET /x?q=secret"}))
    )
    assert "secret" not in queryless["message"]
    configure_logging("INFO")
    configure_logging("DEBUG")


class CheckpointCollection:
    def __init__(self, document: Mapping[str, object] | None = None) -> None:
        self.document = document
        self.result = type("Result", (), {"matched_count": 1, "upserted_id": None})()
        self.error: Exception | None = None

    async def find_one(self, _query: Mapping[str, object]) -> Mapping[str, object] | None:
        if self.error:
            raise self.error
        return self.document

    async def replace_one(self, *_args: object, **_kwargs: object) -> object:
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_checkpoint_store_decodes_optional_fields_and_owner_loss() -> None:
    from event_platform.search.projection import ProjectionCheckpoint

    now = datetime(2026, 1, 1)
    document = {
        "projector": "p",
        "resume_token": {"_data": "x"},
        "updated_at": now,
        "last_projected_event_at": now,
        "state": "degraded",
        "failure_code": "checkpoint_unavailable",
        "owner": "worker-a",
        "generation": 2,
    }
    collection = CheckpointCollection(document)
    store = MongoProjectionCheckpointStore(collection)  # type: ignore[arg-type]
    loaded = await store.load("p")
    assert loaded is not None
    assert loaded.updated_at.tzinfo is UTC
    assert loaded.owner == "worker-a"
    for invalid in (
        {**document, "updated_at": "bad"},
        {**document, "state": "unknown"},
        {**document, "failure_code": "unknown"},
        {**document, "generation": -1},
        {**document, "last_projected_event_at": "bad"},
    ):
        collection.document = invalid
        with pytest.raises(Exception, match="checkpoint_invalid"):
            await store.load("p")
    collection.document = None
    assert await store.load("p") is None
    collection.result = type("Result", (), {"matched_count": 0, "upserted_id": None})()
    with pytest.raises(Exception, match="projection_owner_lost"):
        await store.save(
            ProjectionCheckpoint(projector="p", resume_token={"_data": "x"}, updated_at=now)
        )
    collection.error = PyMongoError("dependency")
    with pytest.raises(CheckpointDependencyError):
        await store.load("p")
