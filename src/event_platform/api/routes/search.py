"""Bounded Elasticsearch search API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import ValidationError

from event_platform.api.problems import ProblemResponse
from event_platform.search.search import (
    SearchCursorError,
    SearchDependencyError,
    SearchPage,
    SearchQuery,
)

router = APIRouter(tags=["events"])


def _request_uuid(request: Request) -> UUID:
    return UUID(str(getattr(request.state, "request_id", uuid4())))


@router.get(
    "/events/search",
    response_model=SearchPage,
    responses={
        422: {
            "description": "Request validation failed",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        503: {
            "description": "Search dependency is unavailable",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
    },
)
async def search_events(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=256)],
    event_type: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    user_id: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SearchPage:
    request_id = _request_uuid(request)
    try:
        query = SearchQuery(
            q=q,
            event_type=event_type,
            user_id=user_id,
            start=start,
            end=end,
            limit=limit,
            cursor=cursor,
        )
    except (ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="search input is invalid"
        ) from None
    service = getattr(request.app.state, "search_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search is temporarily unavailable",
            headers={"Retry-After": "1"},
        )
    try:
        return cast(SearchPage, await service.search(query, request_id=request_id))
    except SearchCursorError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="search input is invalid"
        ) from None
    except (SearchDependencyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
