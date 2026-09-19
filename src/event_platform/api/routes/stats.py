"""Canonical MongoDB event statistics API."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from event_platform.api.problems import ProblemResponse
from event_platform.storage.mongo import MongoDependencyError

Bucket = Literal["hour", "day", "week"]
UTC_TIMEZONE = "UTC"
DEFAULT_RANGE = timedelta(days=1)
MAX_RANGE = timedelta(days=366)
MAX_POINTS = 10_000
MAX_AGGREGATION_TIME_MS = 5_000

router = APIRouter(tags=["events"])


class AnalyticsRange(BaseModel):
    """Inclusive, bounded UTC range used by the aggregation."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> AnalyticsRange:
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError("analytics timestamps must be normalized to UTC")
        if self.start > self.end:
            raise ValueError("analytics start must not exceed end")
        if self.end - self.start > MAX_RANGE:
            raise ValueError("analytics range must not exceed 366 days")
        return self


class StatsPoint(BaseModel):
    bucket: datetime
    event_type: Annotated[str, Field(min_length=1, max_length=128)]
    count: int = Field(gt=0)


class StatsResponse(BaseModel):
    bucket: Bucket
    timezone: Literal["UTC"]
    start: datetime
    end: datetime
    points: list[StatsPoint]
    request_id: UUID


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def effective_range(
    start: datetime | None, end: datetime | None, *, now: datetime | None = None
) -> AnalyticsRange:
    if (start is None) != (end is None):
        raise ValueError("start and end must be supplied together")
    if start is None and end is None:
        effective_end = now or _utc_now()
        start = effective_end - DEFAULT_RANGE
        end = effective_end
    return AnalyticsRange(start=start, end=end)


def build_stats_pipeline(
    analytics_range: AnalyticsRange, bucket: Bucket
) -> list[dict[str, object]]:
    """Build the bounded Mongo pipeline without loading raw events."""

    date_trunc: dict[str, object] = {
        "date": "$timestamp",
        "unit": bucket,
        "binSize": 1,
        "timezone": UTC_TIMEZONE,
    }
    if bucket == "week":
        date_trunc["startOfWeek"] = "monday"
    truncation = {"$dateTrunc": date_trunc}
    return [
        {
            "$match": {
                "timestamp": {
                    "$gte": analytics_range.start,
                    "$lte": analytics_range.end,
                }
            }
        },
        {
            "$group": {
                "_id": {
                    "bucket": truncation,
                    "event_type": "$event_type",
                },
                "count": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "bucket": "$_id.bucket",
                "event_type": "$_id.event_type",
                "count": 1,
            }
        },
        {"$sort": {"bucket": 1, "event_type": 1}},
        {"$limit": MAX_POINTS + 1},
    ]


def _request_uuid(request: Request) -> UUID:
    return UUID(str(getattr(request.state, "request_id", uuid4())))


def _invalid_stats_query() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="statistics query is invalid",
    )


def _decode_point(document: Mapping[str, object]) -> StatsPoint:
    values = dict(document)
    bucket = values.get("bucket")
    if isinstance(bucket, datetime) and bucket.tzinfo is None:
        values["bucket"] = bucket.replace(tzinfo=UTC)
    try:
        point = StatsPoint.model_validate(values)
    except (ValidationError, ValueError, TypeError):
        raise MongoDependencyError("decode_analytics") from None
    if point.bucket.tzinfo is None or point.bucket.utcoffset() != timedelta(0):
        raise MongoDependencyError("decode_analytics")
    return point


@router.get(
    "/events/stats",
    response_model=StatsResponse,
    responses={
        422: {
            "description": "Statistics query validation failed",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        503: {
            "description": "Canonical event storage is unavailable",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
    },
)
async def event_stats(
    request: Request,
    bucket: Annotated[Bucket, Query()] = "hour",
    start: datetime | None = None,
    end: datetime | None = None,
) -> StatsResponse:
    request_id = _request_uuid(request)
    try:
        analytics_range = effective_range(start, end)
    except (ValidationError, ValueError):
        raise _invalid_stats_query() from None

    store = getattr(request.app.state, "event_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="canonical event storage is temporarily unavailable",
            headers={"Retry-After": "1"},
        )
    try:
        documents = await store.aggregate(
            build_stats_pipeline(analytics_range, bucket),
            max_time_ms=MAX_AGGREGATION_TIME_MS,
        )
        if len(documents) > MAX_POINTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="statistics result exceeds the bounded point limit",
            )
        points = [_decode_point(document) for document in documents]
    except MongoDependencyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="canonical event storage is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
    points.sort(key=lambda point: (point.bucket, point.event_type))
    return StatsResponse(
        bucket=bucket,
        timezone=UTC_TIMEZONE,
        start=analytics_range.start,
        end=analytics_range.end,
        points=points,
        request_id=request_id,
    )
