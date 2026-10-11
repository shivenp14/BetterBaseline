"""Thin #66 adapter; shared schemas own validation and the grid service owns orchestration.

#68 owns shared compute/cache guards and the final OpenAPI snapshot.
"""
from fastapi import APIRouter, Request
from importlib.metadata import version
import platform

from ..cache import make_cache_key
from ..schemas import ErrorEnvelope, ScenarioGridRequest, ScenarioGridResponse
from ..services.compute import execute_guarded_computation
from ..services.grid import MAX_COLUMNS, MAX_GRID_CELLS, MAX_ROWS, compute_grid
from ..statistics.errors import StatisticalInputError
from ..statistics.simulation import MAX_ENROLLED_PER_ARM

router = APIRouter(prefix='/api/v1/scenarios', tags=['grid'],
    responses={
        422: {'model': ErrorEnvelope, 'description': 'Validation Error'},
        429: {
            'model': ErrorEnvelope,
            'description': 'Compute Resource Saturated',
            'headers': {'Retry-After': {
                'description': 'Seconds to wait before retrying.',
                'schema': {'type': 'integer'},
            }},
        },
    })
GRID_METHOD_VERSION = 'cohen_h_normal_v1'


@router.post('/grid', response_model=ScenarioGridResponse)
def generate_scenario_grid(request: ScenarioGridRequest, http_request: Request) -> ScenarioGridResponse:
    """Frozen-N grid with exact selected-dropout curve and separate frontier edges.

    frontier_points contains unique interpolated target coordinates for markers;
    use contour_segments for connectivity, never connect the flat list. Off-grid
    planned/selected comparisons remain available even if all grid cells are invalid.
    """
    guard = http_request.app.state.compute_guard

    # Validate before consulting the cache: cached responses must not bypass a
    # stricter app configuration or the hard public contract limits.
    x_steps, y_steps = request.x_baseline.steps, request.y_dropout.steps
    if x_steps > MAX_COLUMNS or y_steps > MAX_ROWS or x_steps * y_steps > MAX_GRID_CELLS:
        raise StatisticalInputError('Grid exceeds public dimensions/cell limit', field='axes', code='RESOURCE_LIMIT')
    guard.check_grid_dimensions(x_steps, y_steps)
    guard.check_enrollment(request.fixed_enrollment.control, request.fixed_enrollment.treatment)
    for arm in ('control', 'treatment'):
        if getattr(request.fixed_enrollment, arm) > MAX_ENROLLED_PER_ARM:
            raise StatisticalInputError(
                f'Enrollment exceeds {MAX_ENROLLED_PER_ARM} per arm',
                field=f'fixed_enrollment.{arm}', code='RESOURCE_LIMIT',
            )

    cache_key = make_cache_key(
        route='/api/v1/scenarios/grid',
        model_version=f'{request.planned_design.model_version}:{GRID_METHOD_VERSION}',
        params={
            'request': request.model_dump(mode='json'),
            'software_versions': {
                'python': platform.python_version(),
                **{package: version(package) for package in ('numpy', 'scipy', 'statsmodels')},
            },
        },
    )
    return execute_guarded_computation(
        compute_grid, request, cache_key=cache_key, guard=guard,
    )
