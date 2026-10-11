"""FastAPI application entrypoint for Better Baseline."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import (
    generic_exception_handler,
    http_exception_handler,
    statistical_input_error_handler,
    validation_error_handler,
)
from .routers import design_router, grid_router, health_router, scenarios_router
from .settings import settings
from .statistics.errors import StatisticalInputError


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
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
    application.include_router(health_router)
    application.include_router(design_router)
    application.include_router(scenarios_router)
    application.include_router(grid_router)

    return application


app = create_app()
