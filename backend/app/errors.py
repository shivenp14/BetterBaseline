"""Standardized error handling and envelope mapping for FastAPI."""

import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .schemas import ErrorDetail, ErrorEnvelope
from .statistics.errors import StatisticalInputError

logger = logging.getLogger(__name__)


def make_error_response(
    status_code: int,
    code: str,
    message: str,
    field: Optional[str] = None,
    recoverable: bool = True,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            field=field,
            recoverable=recoverable,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )


async def statistical_input_error_handler(request: Request, exc: StatisticalInputError) -> JSONResponse:
    code = getattr(exc, "code", "INVALID_MODEL_INPUT") or "INVALID_MODEL_INPUT"
    field = getattr(exc, "field", None)
    return make_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code=code,
        message=str(exc),
        field=field,
        recoverable=True,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    loc = first_error.get("loc", ())
    # Skip 'body' in location if present for cleaner field references
    field_parts = [str(x) for x in loc if x != "body"]
    field = ".".join(field_parts) if field_parts else None
    message = first_error.get("msg", "Validation error")

    return make_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="INVALID_MODEL_INPUT",
        message=f"{field}: {message}" if field else message,
        field=field,
        recoverable=True,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == status.HTTP_404_NOT_FOUND else "HTTP_ERROR"
    return make_error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
        recoverable=exc.status_code < 500,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    return make_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred",
        recoverable=False,
    )
