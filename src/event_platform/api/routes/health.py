"""Foundation liveness route."""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from event_platform.api.problems import ProblemResponse


def _problem_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": ProblemResponse.model_json_schema()}},
    }


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: _problem_response("Resource not found"),
    405: _problem_response("Method not allowed"),
    422: _problem_response("Request validation failed"),
    500: _problem_response("Unexpected application error"),
}

router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"


@router.get(
    "/health/live",
    responses=PROBLEM_RESPONSES,
)
async def get_liveness() -> LiveResponse:
    return LiveResponse()
