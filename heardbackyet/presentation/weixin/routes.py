"""Dynamic iLink onboarding routes owned by the main FastAPI process."""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, HTTPException, Request, status

from heardbackyet.presentation.weixin.runtime import (
    LoginCapacityReached,
)
from heardbackyet.presentation.weixin.schemas import (
    WeixinLoginResponse,
)


router = APIRouter(prefix="/api/v1/weixin", tags=["weixin"])


class WeixinRuntimePort(Protocol):
    async def start_login(self) -> str: ...


def _runtime(request: Request) -> WeixinRuntimePort | None:
    return getattr(request.app.state, "weixin_runtime", None)


@router.post(
    "/login-sessions",
    response_model=WeixinLoginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_weixin_login(
    request: Request,
) -> WeixinLoginResponse:
    runtime = _runtime(request)
    if runtime is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        qrcode_url = await runtime.start_login()
    except LoginCapacityReached:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS) from None
    return WeixinLoginResponse(qrcode_url=qrcode_url)
