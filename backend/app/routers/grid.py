"""Thin #66 adapter; shared schemas own validation and the grid service owns orchestration.

#68 owns shared compute/cache guards and the final OpenAPI snapshot.
"""
from fastapi import APIRouter

from ..schemas import ErrorEnvelope, ScenarioGridRequest, ScenarioGridResponse
from ..services.compute import execute_guarded_computation
from ..services.grid import compute_grid

router = APIRouter(prefix='/api/v1/scenarios', tags=['grid'],
    responses={422: {'model': ErrorEnvelope, 'description': 'Validation Error'}})


@router.post('/grid', response_model=ScenarioGridResponse)
def generate_scenario_grid(request: ScenarioGridRequest) -> ScenarioGridResponse:
    """Frozen-N grid with exact selected-dropout curve and separate frontier edges.

    frontier_points contains unique interpolated target coordinates for markers;
    use contour_segments for connectivity, never connect the flat list. Off-grid
    planned/selected comparisons remain available even if all grid cells are invalid.
    """
    return execute_guarded_computation(compute_grid, request)
