"""Health and metadata routes."""

from typing import Any, Dict
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..settings import Settings, settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = "ok"
    model_version: str = "binary-v1"


class MetaResponse(BaseModel):
    app_name: str
    app_version: str
    model_version: str
    analytical_method: str = "cohen_h_normal_v1"
    simulation_method: str = "pooled_two_proportion_z_v1"


def _resolve_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", settings)


@router.get("/healthz", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    app_settings = _resolve_settings(request)
    return HealthResponse(status="ok", model_version=app_settings.model_version)


@router.get("/api/v1/meta", response_model=MetaResponse)
def get_metadata(request: Request) -> MetaResponse:
    app_settings = _resolve_settings(request)
    return MetaResponse(
        app_name=app_settings.app_name,
        app_version=app_settings.app_version,
        model_version=app_settings.model_version,
    )
