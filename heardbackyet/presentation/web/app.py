from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from heardbackyet.paths import STATIC_DIR
from heardbackyet.presentation.web.config import load_api_allowed_frontend_origins
from heardbackyet.presentation.web.routes import (
    ReadinessService,
    UserQueryService,
    router as core_router,
)
from heardbackyet.presentation.web.schemas import ErrorResponse
from heardbackyet.presentation.weixin.config import WeixinSettings
from heardbackyet.presentation.weixin.routes import router as weixin_router
from heardbackyet.presentation.weixin.runtime import WeixinRuntime

LOGGER = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    """JSON response compatible with clients that require an explicit charset."""

    media_type = "application/json; charset=utf-8"


class ApiRuntimePort(Protocol):
    query_service: UserQueryService
    readiness_service: ReadinessService

    def close(self) -> None: ...


ApiRuntimeFactory = Callable[[], ApiRuntimePort]


def _default_runtime_factory() -> ApiRuntimePort:
    # Keep model and database configuration lazy so importing the ASGI app is safe.
    from heardbackyet.bootstrap import build_api_runtime

    return build_api_runtime()


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    error = ErrorResponse(code=code, message=message)
    return UTF8JSONResponse(
        status_code=status_code,
        content=error.model_dump(),
        headers=headers,
    )


def create_app(
    *,
    query_service: UserQueryService | None = None,
    readiness_service: ReadinessService | None = None,
    runtime_factory: ApiRuntimeFactory | None = None,
) -> FastAPI:
    """Create the ASGI app and own its runtime and HTTP-wide behavior."""
    if query_service is not None and runtime_factory is not None:
        raise ValueError("provide query_service or runtime_factory, not both")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime: ApiRuntimePort | None = None
        weixin_runtime: WeixinRuntime | None = None
        try:
            if query_service is None:
                runtime = (runtime_factory or _default_runtime_factory)()
                app.state.query_service = runtime.query_service
                app.state.readiness_service = runtime.readiness_service
            else:
                app.state.query_service = query_service
                if readiness_service is None:
                    raise ValueError("readiness_service is required with query_service")
                app.state.readiness_service = readiness_service

            weixin_settings = WeixinSettings.from_env()
            weixin_runtime = WeixinRuntime(
                app.state.query_service,
                weixin_settings,
            )
            await weixin_runtime.start()
            app.state.weixin_runtime = weixin_runtime
            yield
        finally:
            if weixin_runtime is not None:
                await weixin_runtime.close()
            if runtime is not None:
                runtime.close()

    application = FastAPI(
        title="HeardBackYet API",
        version="1.0.0",
        lifespan=lifespan,
        default_response_class=UTF8JSONResponse,
    )

    allowed_frontend_origins = load_api_allowed_frontend_origins()
    if allowed_frontend_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_frontend_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation_error",
            message="The request body is invalid.",
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        known_errors = {
            status.HTTP_404_NOT_FOUND: ("not_found", "Route not found."),
            status.HTTP_405_METHOD_NOT_ALLOWED: (
                "method_not_allowed",
                "HTTP method not allowed.",
            ),
            status.HTTP_503_SERVICE_UNAVAILABLE: (
                "dependencies_unavailable",
                "A query dependency is unavailable.",
            ),
        }
        code, message = known_errors.get(
            error.status_code,
            ("http_error", "The HTTP request could not be completed."),
        )
        return _error_response(
            status_code=error.status_code,
            code=code,
            message=message,
            headers=error.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        LOGGER.error(
            "response workflow failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="response_unavailable",
            message="The response could not be generated.",
        )

    @application.get("/", include_in_schema=False, response_class=FileResponse)
    def frontend() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html",
            media_type="text/html; charset=utf-8",
        )

    application.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR),
        name="static",
    )
    application.include_router(core_router)
    application.include_router(weixin_router)
    return application


app = create_app()
