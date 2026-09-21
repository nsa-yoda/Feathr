"""Real MongoDB aggregation coverage for Feature 009."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pymongo import AsyncMongoClient

from event_platform.api.routes.stats import AnalyticsRange, build_stats_pipeline
from event_platform.domain.events import CanonicalEvent, EventInput
from event_platform.storage.mongo import MongoEventStore
from tests.integration.support import drop_database, new_namespace, require_mongo

pytestmark = pytest.mark.integration


def make_event(event_id: UUID, timestamp: datetime, event_type: str) -> CanonicalEvent:
    input_event = EventInput.model_validate(
        {
            "event_type": event_type,
            "timestamp": timestamp.isoformat(),
            "user_id": "analytics-integration",
            "source_url": "https://example.test/analytics",
            "metadata": {"source": "integration"},
        }
    )
    return CanonicalEvent.from_input(input_event, event_id=event_id, ingested_at=timestamp)


def as_utc(value: object) -> datetime:
    assert isinstance(value, datetime)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_real_mongo_date_trunc_counts_hour_day_and_monday_week() -> None:
    uri = os.getenv("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI is not configured")
    await require_mongo(uri)

    client = AsyncMongoClient(uri)
    namespace = new_namespace()
    database = client[namespace.database]
    collection = database[f"analytics_{uuid4().hex}"]
    store = MongoEventStore(collection)
    sunday = datetime(2026, 1, 4, 23, 59, tzinfo=UTC)
    events = [
        make_event(
            UUID("00000000-0000-0000-0000-000000000010"),
            datetime(2026, 1, 4, 22, 59, tzinfo=UTC),
            "outside",
        ),
        make_event(
            UUID("00000000-0000-0000-0000-000000000015"),
            datetime(2026, 1, 4, 23, 0, tzinfo=UTC),
            "boundary-start",
        ),
        make_event(UUID("00000000-0000-0000-0000-000000000011"), sunday, "purchase"),
        make_event(
            UUID("00000000-0000-0000-0000-000000000012"),
            datetime(2026, 1, 5, 0, 15, tzinfo=UTC),
            "pageview",
        ),
        make_event(
            UUID("00000000-0000-0000-0000-000000000013"),
            datetime(2026, 1, 5, 0, 45, tzinfo=UTC),
            "pageview",
        ),
        make_event(
            UUID("00000000-0000-0000-0000-000000000014"),
            datetime(2026, 1, 5, 1, 5, tzinfo=UTC),
            "signup",
        ),
        make_event(
            UUID("00000000-0000-0000-0000-000000000016"),
            datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
            "boundary-end",
        ),
    ]
    analytics_range = AnalyticsRange(
        start=datetime(2026, 1, 4, 23, 0, tzinfo=UTC),
        end=datetime(2026, 1, 5, 2, 0, tzinfo=UTC),
    )
    try:
        for event in events:
            await store.insert(event)
        hourly = await store.aggregate(build_stats_pipeline(analytics_range, "hour"))
        assert [(as_utc(item["bucket"]), item["event_type"], item["count"]) for item in hourly] == [
            (datetime(2026, 1, 4, 23, tzinfo=UTC), "boundary-start", 1),
            (datetime(2026, 1, 4, 23, tzinfo=UTC), "purchase", 1),
            (datetime(2026, 1, 5, 0, tzinfo=UTC), "pageview", 2),
            (datetime(2026, 1, 5, 1, tzinfo=UTC), "signup", 1),
            (datetime(2026, 1, 5, 2, tzinfo=UTC), "boundary-end", 1),
        ]
        daily = await store.aggregate(build_stats_pipeline(analytics_range, "day"))
        assert [(as_utc(item["bucket"]), item["event_type"], item["count"]) for item in daily] == [
            (datetime(2026, 1, 4, tzinfo=UTC), "boundary-start", 1),
            (datetime(2026, 1, 4, tzinfo=UTC), "purchase", 1),
            (datetime(2026, 1, 5, tzinfo=UTC), "boundary-end", 1),
            (datetime(2026, 1, 5, tzinfo=UTC), "pageview", 2),
            (datetime(2026, 1, 5, tzinfo=UTC), "signup", 1),
        ]
        weekly = await store.aggregate(build_stats_pipeline(analytics_range, "week"))
        assert [(as_utc(item["bucket"]), item["event_type"], item["count"]) for item in weekly] == [
            (datetime(2025, 12, 29, tzinfo=UTC), "boundary-start", 1),
            (datetime(2025, 12, 29, tzinfo=UTC), "purchase", 1),
            (datetime(2026, 1, 5, tzinfo=UTC), "boundary-end", 1),
            (datetime(2026, 1, 5, tzinfo=UTC), "pageview", 2),
            (datetime(2026, 1, 5, tzinfo=UTC), "signup", 1),
        ]
    finally:
        try:
            await drop_database(client, database)
        finally:
            await client.close()
