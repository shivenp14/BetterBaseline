"""Middleware for compute concurrency guards, request body caps, and telemetry logging (Issue #68)."""

import logging
import time
from typing import Any, Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..errors import make_error_response
from ..services.compute import ResourceSaturatedError
from ..settings import Settings

logger = logging.getLogger("betterbaseline.telemetry")


class ComputeGuardMiddleware(BaseHTTPMiddleware):
    """Enforces maximum request-body bytes and logs lightweight performance telemetry."""

    def __init__(self, app: Any, cfg: Settings) -> None:
        super().__init__(app)
        self.cfg = cfg

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        # Check Content-Length header against max_body_bytes
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length_val = int(content_length)
                if length_val > self.cfg.max_body_bytes:
                    return make_error_response(
                        status_code=413,
                        code="PAYLOAD_TOO_LARGE",
                        message=f"Request body exceeds maximum allowed size of {self.cfg.max_body_bytes} bytes",
                        recoverable=False,
                    )
            except ValueError:
                pass

        # Also enforce cap on actual received bytes for chunked/streamed bodies
        if request.method in ("POST", "PUT", "PATCH"):
            body_chunks = []
            received = 0
            async for chunk in request.stream():
                received += len(chunk)
                if received > self.cfg.max_body_bytes:
                    return make_error_response(
                        status_code=413,
                        code="PAYLOAD_TOO_LARGE",
                        message=f"Request body exceeds maximum allowed size of {self.cfg.max_body_bytes} bytes",
                        recoverable=False,
                    )
                body_chunks.append(chunk)
            # Reconstruct request body so downstream route handlers can read it
            request._body = b"".join(body_chunks)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except ResourceSaturatedError as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning(
                "compute_saturated route=%s elapsed_ms=%.2f",
                request.url.path,
                elapsed_ms,
            )
            resp = make_error_response(
                status_code=429,
                code="RESOURCE_SATURATED",
                message=exc.message,
                recoverable=True,
            )
            resp.headers["Retry-After"] = str(exc.retry_after)
            return resp

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        # Lightweight telemetry log (never logging private/full request body)
        logger.info(
            "request_completed method=%s path=%s status=%d elapsed_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response
