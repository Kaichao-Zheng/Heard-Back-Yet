from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status

from heardbackyet.presentation.schemas import (
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
    UserQueryRequest,
    UserQueryResponse,
)

router = APIRouter()


class UserQueryService(Protocol):
    """Presentation port for stateless or conversation-linked user queries."""

    def run(
        self,
        user_query: str,
        /,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]: ...


class ReadinessService(Protocol):
    def first_unavailable_dependency(self) -> str | None: ...


def _query_service(request: Request) -> UserQueryService:
    return request.app.state.query_service


def _readiness_service(request: Request) -> ReadinessService:
    return request.app.state.readiness_service


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["operations"],
)
def health() -> HealthResponse:
    # Liveness intentionally avoids model and database calls.
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
    tags=["operations"],
)
def readiness(
    readiness_service: ReadinessService = Depends(_readiness_service),
) -> ReadinessResponse:
    if readiness_service.first_unavailable_dependency() is not None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return ReadinessResponse()


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
    query_service: UserQueryService = Depends(_query_service),
) -> UserQueryResponse:
    if payload.conversation_id is None:
        response = query_service.run(payload.user_query)
    else:
        response = query_service.run(
            payload.user_query,
            conversation_id=payload.conversation_id,
        )
    return UserQueryResponse.model_validate(response)
