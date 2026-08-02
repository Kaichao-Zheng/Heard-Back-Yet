from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, Depends, Request, status

from heardbackyet.presentation.schemas import (
    ErrorResponse,
    HealthResponse,
    UserQueryRequest,
    UserQueryResponse,
)

router = APIRouter()


class UserQueryRunner(Protocol):
    """Presentation port for the single-user-query application capability."""

    def run(self, user_query: str, /) -> dict[str, Any]: ...


def _user_query_runner(request: Request) -> UserQueryRunner:
    return request.app.state.user_query_runner


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["operations"],
)
def health() -> HealthResponse:
    # Liveness intentionally avoids model and database calls.
    return HealthResponse()


@router.post(
    "/api/v1/responses",
    response_model=UserQueryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    tags=["responses"],
)
def create_response(
    payload: UserQueryRequest,
    runner: UserQueryRunner = Depends(_user_query_runner),
) -> UserQueryResponse:
    return UserQueryResponse.model_validate(runner.run(payload.user_query))
