"""#66 orchestration of the frozen-enrollment grid engine and HTTP response models."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import platform

from ..data.provenance import normalize_provenance
from ..schemas import (ContourPoint, ContourSegment, ExpectedRetainedCounts,
    GridAxisSpec, GridDropoutAxisSpec, GridPoint, PowerCurvePoint,
    ScenarioGridRequest, ScenarioGridResponse)
from ..statistics.diagnostics import analytic_diagnostics
from ..statistics.effect import resolve_treatment_risk
from ..statistics.errors import StatisticalInputError
from ..statistics.inputs import Effect, FixedEnrollment
from ..statistics.simulation import MAX_ENROLLED_PER_ARM
from ..statistics.stress_grid import GridCoordinate, GridPoint as StatisticalPoint, stress_grid

MAX_COLUMNS = GridAxisSpec.model_json_schema()['properties']['steps']['maximum']
MAX_ROWS = GridDropoutAxisSpec.model_json_schema()['properties']['steps']['maximum']
MAX_GRID_CELLS = MAX_COLUMNS * MAX_ROWS


def _axis(spec: GridAxisSpec | GridDropoutAxisSpec) -> tuple[float, ...]:
    values = tuple(spec.min + (spec.max - spec.min) * i / (spec.steps - 1)
                   for i in range(spec.steps - 1)) + (spec.max,)
    if any(a >= b for a, b in zip(values, values[1:])):
        raise StatisticalInputError('Axis spacing is too small for distinct points', field='axes')
    return values


def _point(point: StatisticalPoint) -> GridPoint:
    return GridPoint(p_control=point.baseline, dropout=point.dropout,
        power=point.power, is_valid=point.power is not None, is_safe=point.below_target is False,
        expected_evaluable_n=ExpectedRetainedCounts(control=point.expected_evaluable_per_arm,
                                                   treatment=point.expected_evaluable_per_arm),
        invalid_reason=point.invalid_reason)


def compute_grid(request: ScenarioGridRequest) -> ScenarioGridResponse:
    # Bounds precede axis allocation and numerical work. These derive from the
    # published axis contract and the scenario API's per-arm enrollment cap.
    if (request.x_baseline.steps > MAX_COLUMNS or request.y_dropout.steps > MAX_ROWS
            or request.x_baseline.steps * request.y_dropout.steps > MAX_GRID_CELLS):
        raise StatisticalInputError('Grid exceeds public dimensions/cell limit', field='axes', code='RESOURCE_LIMIT')
    if request.fixed_enrollment.control > MAX_ENROLLED_PER_ARM:
        raise StatisticalInputError('Enrollment exceeds public per-arm limit', field='fixed_enrollment', code='RESOURCE_LIMIT')
    x, y = _axis(request.x_baseline), _axis(request.y_dropout)
    design, selected = request.planned_design, request.selected_scenario
    enrollment = FixedEnrollment(request.fixed_enrollment.control, request.fixed_enrollment.treatment)
    planned_coordinate = GridCoordinate(design.control_event_rate, design.dropout.control)
    selected_coordinate = (GridCoordinate(selected.control_event_rate, selected.dropout.control)
                           if selected else GridCoordinate(design.control_event_rate, 0))
    effective = request.effective_grid_effect
    effect = Effect(effective.kind, effective.value)
    result = stress_grid(enrollment, effect, x, y, planned_point=planned_coordinate,
                         selected_point=selected_coordinate, alpha=design.alpha, target_power=design.target_power)
    if result.x_baseline != x or result.y_dropout != y or result.fixed_enrollment != enrollment:
        raise ValueError('Grid engine changed axes or frozen enrollment')
    if len(result.below_target) != len(y) or any(len(row) != len(x) for row in result.below_target):
        raise ValueError('Grid engine returned malformed target mask')
    for powers, below in zip(result.power, result.below_target):
        if any(flag != (power < design.target_power if power is not None else None)
               for power, flag in zip(powers, below)):
            raise ValueError('Grid target mask disagrees with powers')
    if len(result.power_curve) != len(x) or any(point.baseline != baseline or point.dropout != selected_coordinate.dropout
            for point, baseline in zip(result.power_curve, x)):
        raise ValueError('Grid engine returned an incompatible selected-dropout curve')
    planned = result.planned_point
    warnings = list(result.warnings)
    if effective != design.effect:
        # The engine uses one effect for its surface; original planned comparison
        # must retain the design's effect even when the stress effect is changed.
        original = stress_grid(enrollment, Effect(design.effect.kind, design.effect.value),
            (planned_coordinate.baseline,), (planned_coordinate.dropout,),
            planned_point=planned_coordinate, selected_point=planned_coordinate,
            alpha=design.alpha, target_power=design.target_power)
        planned = original.planned_point
        warnings = [message for message in warnings if not message.startswith('Planned point is unavailable:')]
        if planned.invalid_reason:
            warnings.append(f'Planned point is unavailable: {planned.invalid_reason}.')
    for point, point_effect in ((planned, Effect(design.effect.kind, design.effect.value)), (result.selected_point, effect)):
        if point.power is not None:
            treatment = resolve_treatment_risk(point.baseline, point_effect)
            warnings.extend(entry['message'] for entry in analytic_diagnostics(point.baseline, treatment,
                point.expected_evaluable_per_arm, point.expected_evaluable_per_arm, design.alpha)['diagnostics'])
    contours = [ContourSegment(start=ContourPoint(p_control=a.baseline, dropout=a.dropout),
                              end=ContourPoint(p_control=b.baseline, dropout=b.dropout))
                for path in result.frontier_points for a, b in zip(path.points, path.points[1:])]
    warnings = [message.replace('worst-case power and analytic delta are unavailable', 'worst-case power is unavailable') for message in warnings]
    canonical = json.dumps(request.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), allow_nan=False)
    delta = (result.selected_point.power - planned.power if result.selected_point.power is not None and planned.power is not None else None)
    return ScenarioGridResponse(grid_label=result.grid_label,
        fixed_enrollment=request.fixed_enrollment.model_copy(deep=True),
        x_baseline=list(result.x_baseline), y_dropout=list(result.y_dropout),
        power=[list(row) for row in result.power], invalid_mask=[list(row) for row in result.invalid_mask],
        below_target=[list(row) for row in result.below_target], target_power=result.target_power,
        planned_point=_point(planned), selected_point=_point(result.selected_point), analytic_delta=delta,
        frontier_points=[GridPoint(p_control=point.baseline, dropout=point.dropout,
            power=result.target_power, is_safe=True, is_valid=True)
            for point in sorted({point for path in result.frontier_points for point in path.points})],
        contour_segments=contours,
        power_curve=[PowerCurvePoint(p_control=p.baseline, power=p.power, is_valid=p.power is not None) for p in result.power_curve],
        invalid_cell_count=result.invalid_cell_count, worst_case_power=result.worst_case_power,
        warnings=list(dict.fromkeys(warnings)), computed_at=datetime.now(timezone.utc).isoformat(),
        inputs_hash='sha256:' + hashlib.sha256(canonical.encode()).hexdigest(),
        software_versions={'python': platform.python_version(), **{p: version(p) for p in ('numpy', 'scipy', 'statsmodels')}},
        provenance=normalize_provenance(request.provenance))
