"""Health and metadata routes."""

from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel

from ..settings import settings

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


@router.get("/healthz", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", model_version=settings.model_version)


@router.get("/api/v1/meta", response_model=MetaResponse)
def get_metadata() -> MetaResponse:
    return MetaResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        model_version=settings.model_version,
    )
