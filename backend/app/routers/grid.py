"""Scenario grid calculation route scaffold (owned by Issue #66)."""

from fastapi import APIRouter, HTTPException, status

from ..schemas import ScenarioGridRequest, ScenarioGridResponse

router = APIRouter(prefix="/api/v1/scenarios", tags=["grid"])


@router.post("/grid", response_model=ScenarioGridResponse)
def generate_scenario_grid(request: ScenarioGridRequest) -> ScenarioGridResponse:
    """Scaffold endpoint for 2D scenario grid and 1D power curve generation.

    Handoff to Issue #66 (@roland-aranas) for full grid calculation and contour extraction.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Scenario grid endpoint implementation owned by Issue #66.",
    )
