from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from typing import Optional

from .errors import (
    generic_exception_handler,
    http_exception_handler,
    make_error_response,
    statistical_input_error_handler,
    validation_error_handler,
)
from .middleware.compute import ComputeGuardMiddleware
from .routers import design_router, grid_router, health_router, scenarios_router
from .schemas import ErrorEnvelope
from .services.compute import ComputeResourceGuard, ResourceSaturatedError
from .settings import Settings, settings
from .statistics.errors import StatisticalInputError


async def resource_saturated_error_handler(request: Request, exc: ResourceSaturatedError) -> JSONResponse:
    resp = make_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="RESOURCE_SATURATED",
        message=exc.message,
        recoverable=True,
    )
    resp.headers["Retry-After"] = str(exc.retry_after)
    return resp


def create_app(app_settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = app_settings if app_settings is not None else Settings()
    application = FastAPI(
        title=cfg.app_name,
        version=cfg.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    application.state.settings = cfg
    guard = ComputeResourceGuard(
        max_mc_reps=cfg.max_mc_reps,
        max_grid_cells=cfg.max_grid_cells,
        max_enrolled_per_arm=cfg.max_enrolled_per_arm,
        max_concurrent_compute=cfg.max_concurrent_compute,
        cache_capacity=cfg.cache_size,
    )
    application.state.compute_guard = guard

    # Compute guard middleware (payload size, concurrency, telemetry)
    application.add_middleware(ComputeGuardMiddleware, cfg=cfg)

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    application.add_exception_handler(ResourceSaturatedError, resource_saturated_error_handler)
    application.add_exception_handler(StatisticalInputError, statistical_input_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(Exception, generic_exception_handler)

    # Routers
    validation_error_responses = {
        422: {
            "model": ErrorEnvelope,
            "description": "Validation Error",
        }
    }
    scaffold_responses = {
        422: {
            "model": ErrorEnvelope,
            "description": "Validation Error",
        },
        501: {
            "model": ErrorEnvelope,
            "description": "Not Implemented",
        },
    }

    application.include_router(health_router)
    application.include_router(design_router, responses=validation_error_responses)
    application.include_router(scenarios_router, responses=scaffold_responses)
    application.include_router(grid_router, responses=scaffold_responses)

    return application


app = create_app(settings)
