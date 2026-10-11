"""FastAPI application entrypoint for Better Baseline."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from typing import Optional

from .errors import (
    generic_exception_handler,
    http_exception_handler,
    statistical_input_error_handler,
    validation_error_handler,
)
from .routers import design_router, grid_router, health_router, scenarios_router
from .schemas import ErrorEnvelope
from .settings import Settings, settings
from .statistics.errors import StatisticalInputError


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

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
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

    application.include_router(health_router)
    application.include_router(design_router, responses=validation_error_responses)
    application.include_router(scenarios_router, responses=validation_error_responses)
    application.include_router(grid_router, responses=validation_error_responses)

    return application


app = create_app(settings)
