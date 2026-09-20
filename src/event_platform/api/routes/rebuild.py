"""Read-only rebuild status API."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from event_platform.api.problems import ProblemResponse
from event_platform.search.rebuild import RebuildRecord
from event_platform.storage.rebuilds import RebuildStorageError

router = APIRouter(tags=["search"])


@router.get(
    "/events/search/rebuild",
    response_model=RebuildRecord,
    responses={
        404: {
            "description": "No rebuild record",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
        503: {
            "description": "Rebuild state is unavailable",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        },
    },
)
async def rebuild_status(request: Request, rebuild_id: UUID | None = None) -> RebuildRecord:
    store = getattr(request.app.state, "rebuild_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rebuild status is temporarily unavailable",
            headers={"Retry-After": "1"},
        )
    try:
        record = await (store.get(rebuild_id) if rebuild_id is not None else store.latest())
    except RebuildStorageError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rebuild status is temporarily unavailable",
            headers={"Retry-After": "1"},
        ) from None
    if record is None or (rebuild_id is not None and record.rebuild_id != rebuild_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="rebuild record was not found"
        )
    return cast(RebuildRecord, record)
