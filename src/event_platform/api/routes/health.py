"""Foundation liveness route."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from event_platform.api.problems import ProblemResponse

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"


@router.get(
    "/health/live",
    responses={
        500: {
            "description": "Unexpected application error",
            "content": {
                "application/problem+json": {"schema": ProblemResponse.model_json_schema()}
            },
        }
    },
)
async def get_liveness() -> LiveResponse:
    return LiveResponse()
