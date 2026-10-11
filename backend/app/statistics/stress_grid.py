"""Deterministic power surfaces at frozen equal-arm enrollment.

These immutable records are local statistical values, not HTTP schemas. Axes
must be strictly increasing; rows index dropout and columns index baseline.
Contours use piecewise-linear edge interpolation (marching squares), not an
exact solution of the analytical power function. All four cell corners must
be valid. Exact-target values belong to the >= target side; isolated target
vertices and flat target plateaus do not create zero-length contours. Saddle
cells use their mean corner power to choose connectivity (ties go above).
At branching exact-target vertices, paths stop rather than joining arbitrarily.
"""

from collections.abc import Sequence
from dataclasses import dataclass
import math

from .analytic import COHEN_H_NORMAL_METHOD, COHEN_H_NORMAL_VERSION, analytic_power
from .effect import resolve_treatment_risk
from .errors import StatisticalInputError
from .inputs import Effect, FixedEnrollment, expected_retained_count
from .validation import probability

MAX_BASELINE_POINTS = 81
MAX_DROPOUT_POINTS = 61
MAX_GRID_CELLS = MAX_BASELINE_POINTS * MAX_DROPOUT_POINTS
GRID_LABEL = "expected_count_approximation"


@dataclass(frozen=True)
class GridCoordinate:
    baseline: float
    dropout: float


@dataclass(frozen=True)
class GridPoint:
    baseline: float
    dropout: float
    power: float | None
    expected_evaluable_per_arm: int
    invalid_reason: str | None


@dataclass(frozen=True)
class ContourSegment:
    """One ordered connected path; closed paths repeat their first point."""

    points: tuple[GridCoordinate, ...]


@dataclass(frozen=True)
class StressGridResult:
    model_version: str
    method: str
    method_version: str
    grid_label: str
    fixed_enrollment: FixedEnrollment
    x_baseline: tuple[float, ...]
    y_dropout: tuple[float, ...]
    power: tuple[tuple[float | None, ...], ...]
    invalid_mask: tuple[tuple[bool, ...], ...]
    below_target: tuple[tuple[bool | None, ...], ...]
    target_power: float
    planned_point: GridPoint
    selected_point: GridPoint
    analytic_delta: float | None
    power_curve: tuple[GridPoint, ...]
    frontier_points: tuple[ContourSegment, ...]
    worst_case_power: float | None
    invalid_cell_count: int
    warnings: tuple[str, ...]


def _axis(values: Sequence[float], *, field: str, maximum: int, allow_zero: bool) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not 1 <= len(values) <= maximum:
        raise StatisticalInputError(f"Expected 1 to {maximum} axis points", field=field)
    axis = tuple(probability(value, field=f"{field}[{index}]", allow_zero=allow_zero)
                 for index, value in enumerate(values))
    if any(left >= right for left, right in zip(axis, axis[1:])):
        raise StatisticalInputError("Axis must be strictly increasing without duplicates", field=field)
    return axis


def _coordinate(value: GridCoordinate, *, field: str) -> GridCoordinate:
    if not isinstance(value, GridCoordinate):
        raise StatisticalInputError("Expected a GridCoordinate", field=field)
    return GridCoordinate(
        probability(value.baseline, field=f"{field}.baseline"),
        probability(value.dropout, field=f"{field}.dropout", allow_zero=True),
    )


def _evaluate(enrollment: int, effect: Effect, baseline: float, dropout: float, alpha: float) -> GridPoint:
    retained = expected_retained_count(enrollment, dropout)
    try:
        treatment = resolve_treatment_risk(baseline, effect)
    except StatisticalInputError as error:
        # Only impossible transformed risks become unavailable model points.
        # Unexpected failures and structural input errors must propagate.
        if error.code != "INVALID_MODEL_INPUT" or error.field not in ("effect.value", "treatment_event_rate"):
            raise
        return GridPoint(baseline, dropout, None, retained, "INVALID_EFFECT_AT_BASELINE")
    if retained < 2:
        return GridPoint(baseline, dropout, None, retained, "INSUFFICIENT_EXPECTED_RETAINED")
    power = analytic_power(baseline, treatment, retained, retained, alpha).power
    if not math.isfinite(power) or not 0 <= power <= 1:
        raise ArithmeticError("Analytical power returned an invalid numerical value")
    return GridPoint(baseline, dropout, power, retained, None)


def _frontier(
    x: tuple[float, ...], y: tuple[float, ...],
    power: tuple[tuple[float | None, ...], ...], target: float,
) -> tuple[ContourSegment, ...]:
    """Extract and stitch only locally valid target-bracketing segments.

    Node keys name grid vertices/edges rather than rounded coordinates so
    neighboring cells agree exactly without joining merely nearby paths.
    """
    nodes: dict[tuple[str, int, int], GridCoordinate] = {}
    edges: set[tuple[tuple[str, int, int], tuple[str, int, int]]] = set()
    for row in range(len(y) - 1):
        for column in range(len(x) - 1):
            corners = ((row, column), (row, column + 1), (row + 1, column + 1), (row + 1, column))
            values = [power[r][c] for r, c in corners]
            if any(value is None for value in values):
                continue
            valid_values = [float(value) for value in values if value is not None]
            above = [value >= target for value in valid_values]
            crossing: dict[int, tuple[str, int, int]] = {}
            for edge in range(4):
                following = (edge + 1) % 4
                if above[edge] == above[following]:
                    continue
                r1, c1 = corners[edge]
                r2, c2 = corners[following]
                v1, v2 = valid_values[edge], valid_values[following]
                if v1 == target:
                    key = ("v", r1, c1)
                    coordinate = GridCoordinate(x[c1], y[r1])
                elif v2 == target:
                    key = ("v", r2, c2)
                    coordinate = GridCoordinate(x[c2], y[r2])
                else:
                    key = ("h", r1, min(c1, c2)) if r1 == r2 else ("d", min(r1, r2), c1)
                    # Canonical endpoint order makes shared-edge interpolation
                    # bit-for-bit identical across adjacent cells.
                    if (r1, c1) > (r2, c2):
                        r1, c1, r2, c2, v1, v2 = r2, c2, r1, c1, v2, v1
                    fraction = (target - v1) / (v2 - v1)
                    coordinate = GridCoordinate(
                        x[c1] + fraction * (x[c2] - x[c1]),
                        y[r1] + fraction * (y[r2] - y[r1]),
                    )
                nodes[key] = coordinate
                crossing[edge] = key
            pairs: list[tuple[int, int]] = []
            if len(crossing) == 2:
                pairs.append(tuple(crossing))
            elif len(crossing) == 4:
                center_above = sum(valid_values) / 4 >= target
                pairs.extend(((corner - 1) % 4, corner) for corner in range(4)
                             if above[corner] != center_above)
            for first, second in pairs:
                a, b = crossing[first], crossing[second]
                if a != b and nodes[a] != nodes[b]:
                    edges.add(tuple(sorted((a, b))))

    adjacency: dict[tuple[str, int, int], set[tuple[str, int, int]]] = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    visited: set[tuple[tuple[str, int, int], tuple[str, int, int]]] = set()
    segments: list[ContourSegment] = []

    def trace(start: tuple[str, int, int], following: tuple[str, int, int]) -> None:
        path = [nodes[start]]
        previous, current = start, following
        while True:
            edge = tuple(sorted((previous, current)))
            if edge in visited:
                break
            visited.add(edge)
            path.append(nodes[current])
            if current == start or len(adjacency[current]) != 2:
                break
            candidates = sorted(adjacency[current] - {previous})
            previous, current = current, candidates[0]
        segments.append(ContourSegment(tuple(path)))

    # Open paths and branches first, then closed loops. No arbitrary branch join.
    for start in sorted(adjacency):
        if len(adjacency[start]) == 2:
            continue
        for following in sorted(adjacency[start]):
            if tuple(sorted((start, following))) not in visited:
                trace(start, following)
    for a, b in sorted(edges):
        if (a, b) not in visited:
            trace(a, b)
    return tuple(segments)


def stress_grid(
    fixed_enrollment: FixedEnrollment,
    effect: Effect,
    baselines: Sequence[float],
    dropout_rates: Sequence[float],
    *,
    planned_point: GridCoordinate,
    selected_point: GridCoordinate,
    alpha: float = .05,
    target_power: float = .80,
) -> StressGridResult:
    """Evaluate a declared scenario domain without resizing the planned N.

    The power curve uses each baseline at the exact selected dropout. Points
    may lie outside the axes and are evaluated directly, not snapped. Delta is
    selected minus planned power as a fraction (multiply by 100 for pp).
    All-invalid domains have no extrema/frontier; independent valid off-grid
    points still retain their own calculated values. Invalid mask cells have
    power=None and below_target=None, never a fabricated low-power value.
    """
    if not isinstance(fixed_enrollment, FixedEnrollment):
        raise StatisticalInputError("Expected equal FixedEnrollment input", field="fixed_enrollment")
    if not isinstance(effect, Effect):
        raise StatisticalInputError("Expected an Effect input", field="effect")
    alpha_value = probability(alpha, field="alpha")
    target = probability(target_power, field="target_power")
    if target <= alpha_value:
        raise StatisticalInputError("Target power must be greater than alpha", field="target_power")
    x = _axis(baselines, field="baselines", maximum=MAX_BASELINE_POINTS, allow_zero=False)
    y = _axis(dropout_rates, field="dropout_rates", maximum=MAX_DROPOUT_POINTS, allow_zero=True)
    if len(x) * len(y) > MAX_GRID_CELLS:
        raise StatisticalInputError("Grid exceeds the cell limit", field="grid")
    planned = _coordinate(planned_point, field="planned_point")
    selected = _coordinate(selected_point, field="selected_point")
    enrollment = fixed_enrollment.control
    points = tuple(tuple(_evaluate(enrollment, effect, baseline, dropout, alpha_value)
                         for baseline in x) for dropout in y)
    powers = tuple(tuple(point.power for point in row) for row in points)
    invalid = tuple(tuple(point.power is None for point in row) for row in points)
    below = tuple(tuple(None if point.power is None else point.power < target for point in row) for row in points)
    curve = tuple(_evaluate(enrollment, effect, baseline, selected.dropout, alpha_value) for baseline in x)
    planned_result = _evaluate(enrollment, effect, planned.baseline, planned.dropout, alpha_value)
    selected_result = _evaluate(enrollment, effect, selected.baseline, selected.dropout, alpha_value)
    valid_powers = [value for row in powers for value in row if value is not None]
    invalid_count = sum(sum(row) for row in invalid)
    warnings = ["Expected-count approximation: floored expected retention is not a simulated or guaranteed retained count."]
    if invalid_count:
        warnings.append(f"{invalid_count} grid cells are unavailable due to invalid effect or insufficient expected retained counts.")
    if not valid_powers:
        warnings.append("All grid cells are invalid; worst-case power is unavailable and the frontier is empty.")
    if any(point.power is None for point in curve):
        warnings.append("Some selected-dropout power-curve points are unavailable.")
    for name, point in (("Planned", planned_result), ("Selected", selected_result)):
        if point.power is None:
            warnings.append(f"{name} point is unavailable: {point.invalid_reason}.")
    delta = None if planned_result.power is None or selected_result.power is None else selected_result.power - planned_result.power
    return StressGridResult(
        model_version="binary-v1", method=COHEN_H_NORMAL_METHOD,
        method_version=COHEN_H_NORMAL_VERSION, grid_label=GRID_LABEL,
        fixed_enrollment=fixed_enrollment, x_baseline=x, y_dropout=y,
        power=powers, invalid_mask=invalid, below_target=below, target_power=target,
        planned_point=planned_result, selected_point=selected_result, analytic_delta=delta,
        power_curve=curve, frontier_points=_frontier(x, y, powers, target),
        worst_case_power=min(valid_powers) if valid_powers else None,
        invalid_cell_count=invalid_count, warnings=tuple(warnings),
    )
