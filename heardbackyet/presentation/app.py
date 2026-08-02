from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from heardbackyet.paths import STATIC_DIR
from heardbackyet.presentation.routes import UserQueryRunner, router
from heardbackyet.presentation.schemas import ErrorResponse

LOGGER = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    """JSON response compatible with clients that require an explicit charset."""

    media_type = "application/json; charset=utf-8"


class RuntimePort(Protocol):
    runner: UserQueryRunner

    def close(self) -> None: ...


RuntimeFactory = Callable[[], RuntimePort]


def _default_runtime_factory() -> RuntimePort:
    # Keep model and database configuration lazy so importing the ASGI app is safe.
    from heardbackyet.response.answer_query import build_answer_query_runtime

    return build_answer_query_runtime()


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
    user_query_runner: UserQueryRunner | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> FastAPI:
    """Create the ASGI app and own its runtime and HTTP-wide behavior."""
    if user_query_runner is not None and runtime_factory is not None:
        raise ValueError("provide user_query_runner or runtime_factory, not both")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime: RuntimePort | None = None
        if user_query_runner is None:
            runtime = (runtime_factory or _default_runtime_factory)()
            app.state.user_query_runner = runtime.runner
        else:
            app.state.user_query_runner = user_query_runner
        try:
            yield
        finally:
            if runtime is not None:
                runtime.close()

    application = FastAPI(
        title="HeardBackYet API",
        version="1.0.0",
        lifespan=lifespan,
        default_response_class=UTF8JSONResponse,
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
    application.include_router(router)
    return application


app = create_app()
