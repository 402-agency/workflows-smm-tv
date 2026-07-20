"""Application exceptions and FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

_log = get_logger("errors")


class AppError(Exception):
    """Base class for expected, mapped application errors."""

    status_code = 500
    message = "Internal server error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)
        if message:
            self.message = message


class NotFoundError(AppError):
    status_code = 404
    message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    message = "Conflict"


class ConfigurationError(AppError):
    status_code = 503
    message = "Service not configured"


class ProviderError(AppError):
    """An external provider / upstream call failed."""

    status_code = 502
    message = "Upstream provider error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        _log.warning("app_error", type=type(exc).__name__, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": type(exc).__name__, "detail": exc.message},
        )
