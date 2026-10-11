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
from itertools import product
import math
from typing import Literal

from .analytic import analytic_power
from .effect import resolve_treatment_risk
from .errors import StatisticalInputError
from .inputs import Effect, FixedEnrollment, expected_retained_count
from .validation import probability

GRID_LABEL = "expected_count_approximation"


@dataclass(frozen=True, order=True)
class GridCoordinate:
    baseline: float
    dropout: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline", probability(self.baseline, field="baseline"))
        object.__setattr__(self, "dropout", probability(self.dropout, field="dropout", allow_zero=True))


@dataclass(frozen=True)
class GridPoint(GridCoordinate):
    power: float | None
    expected_evaluable_per_arm: int
    invalid_reason: str | None
    below_target: bool | None


@dataclass(frozen=True)
class ContourSegment:
    """Canonical connected path; closed paths repeat their smallest point."""

    # Open paths start at the lexicographically smaller endpoint. Closed paths
    # start at their smallest coordinate and choose the smaller orientation.

    points: tuple[GridCoordinate, ...]


@dataclass(frozen=True)
class StressGridResult:
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


def _axis(values: Sequence[float], *, field: str, allow_zero: bool) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise StatisticalInputError("Expected a nonempty sequence of axis points", field=field)
    axis = tuple(probability(value, field=f"{field}[{index}]", allow_zero=allow_zero)
                 for index, value in enumerate(values))
    if any(left >= right for left, right in zip(axis, axis[1:])):
        raise StatisticalInputError("Axis must be strictly increasing without duplicates", field=field)
    return axis


def _evaluate(enrollment: int, effect: Effect, coordinate: GridCoordinate, alpha: float, target: float) -> GridPoint:
    baseline, dropout = coordinate.baseline, coordinate.dropout
    retained = expected_retained_count(enrollment, dropout)
    try:
        treatment = resolve_treatment_risk(baseline, effect)
    except StatisticalInputError as error:
        # Only impossible transformed risks become unavailable model points.
        # Unexpected failures and structural input errors must propagate.
        if error.code != "INVALID_MODEL_INPUT" or error.field not in ("effect.value", "treatment_event_rate"):
            raise
        return GridPoint(baseline, dropout, None, retained, "INVALID_EFFECT_AT_BASELINE", None)
    if retained < 2:
        return GridPoint(baseline, dropout, None, retained, "INSUFFICIENT_EXPECTED_RETAINED", None)
    power = analytic_power(baseline, treatment, retained, retained, alpha).power
    if not math.isfinite(power) or not 0 <= power <= 1:
        raise ArithmeticError("Analytical power returned an invalid numerical value")
    return GridPoint(baseline, dropout, power, retained, None, power < target)


@dataclass(frozen=True, order=True)
class _ContourNode:
    kind: Literal["vertex", "horizontal_edge", "vertical_edge"]
    row: int
    column: int


@dataclass(frozen=True)
class _Intersection:
    node: _ContourNode
    coordinate: GridCoordinate


def _edge_intersection(
    x: tuple[float, ...], y: tuple[float, ...],
    first: tuple[int, int], second: tuple[int, int],
    v1: float, v2: float, target: float,
) -> _Intersection:
    r1, c1 = first
    r2, c2 = second
    if v1 == target:
        return _Intersection(_ContourNode("vertex", r1, c1), GridCoordinate(x[c1], y[r1]))
    if v2 == target:
        return _Intersection(_ContourNode("vertex", r2, c2), GridCoordinate(x[c2], y[r2]))
    kind = "horizontal_edge" if r1 == r2 else "vertical_edge"
    node = _ContourNode(kind, min(r1, r2), min(c1, c2))
    # Shared edges use identical arithmetic in both adjacent cells.
    if first > second:
        r1, c1, r2, c2, v1, v2 = r2, c2, r1, c1, v2, v1
    fraction = (target - v1) / (v2 - v1)
    return _Intersection(node, GridCoordinate(
        x[c1] + fraction * (x[c2] - x[c1]),
        y[r1] + fraction * (y[r2] - y[r1]),
    ))


def _cell_segments(
    x: tuple[float, ...], y: tuple[float, ...],
    power: tuple[tuple[float | None, ...], ...], target: float,
    row: int, column: int,
) -> tuple[tuple[_Intersection, _Intersection], ...]:
    corners = ((row, column), (row, column + 1), (row + 1, column + 1), (row + 1, column))
    values = [power[r][c] for r, c in corners]
    if any(value is None for value in values):
        return ()
    valid_values = [float(value) for value in values if value is not None]
    above = [value >= target for value in valid_values]
    crossing: dict[int, _Intersection] = {}
    for edge in range(4):
        following = (edge + 1) % 4
        if above[edge] != above[following]:
            crossing[edge] = _edge_intersection(
                x, y, corners[edge], corners[following], valid_values[edge], valid_values[following], target,
            )
    pairs = []
    if len(crossing) == 2:
        pairs.append(tuple(crossing))
    elif len(crossing) == 4:
        center_above = sum(valid_values) / 4 >= target
        pairs.extend(((corner - 1) % 4, corner) for corner in range(4)
                     if above[corner] != center_above)
    return tuple((crossing[a], crossing[b]) for a, b in pairs
                 if crossing[a].coordinate != crossing[b].coordinate)


def _canonical_path(path: list[GridCoordinate]) -> ContourSegment:
    if path[0] != path[-1]:
        return ContourSegment(min(tuple(path), tuple(reversed(path))))
    ring = path[:-1]
    start = ring.index(min(ring))
    forward = tuple(ring[start:] + ring[:start])
    backward = (forward[0],) + tuple(reversed(forward[1:]))
    ordered = min(forward, backward)
    return ContourSegment(ordered + (ordered[0],))


def _trace_path(
    start: _ContourNode, following: _ContourNode,
    nodes: dict[_ContourNode, GridCoordinate],
    adjacency: dict[_ContourNode, set[_ContourNode]],
    visited: set[tuple[_ContourNode, _ContourNode]],
) -> ContourSegment:
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
        previous, current = current, next(iter(adjacency[current] - {previous}))
    return _canonical_path(path)


def _frontier(
    x: tuple[float, ...], y: tuple[float, ...],
    power: tuple[tuple[float | None, ...], ...], target: float,
) -> tuple[ContourSegment, ...]:
    """Stitch valid cells by shared topology, then sort canonical paths."""
    nodes: dict[_ContourNode, GridCoordinate] = {}
    edges: set[tuple[_ContourNode, _ContourNode]] = set()
    cells = product(range(len(y) - 1), range(len(x) - 1))
    for row, column in cells:
        for first, second in _cell_segments(x, y, power, target, row, column):
            nodes[first.node], nodes[second.node] = first.coordinate, second.coordinate
            edges.add(tuple(sorted((first.node, second.node))))
    adjacency: dict[_ContourNode, set[_ContourNode]] = {}
    for a, b in edges:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    visited: set[tuple[_ContourNode, _ContourNode]] = set()
    segments = []
    # Open paths and branches first; remaining edges form closed loops.
    starts = ((start, following) for start in sorted(adjacency) if len(adjacency[start]) != 2
              for following in sorted(adjacency[start]))
    for start, following in starts:
        if tuple(sorted((start, following))) not in visited:
            segments.append(_trace_path(start, following, nodes, adjacency, visited))
    for a, b in sorted(edges):
        if (a, b) not in visited:
            segments.append(_trace_path(a, b, nodes, adjacency, visited))
    return tuple(sorted(segments, key=lambda segment: segment.points))


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
    All-invalid domains have no extrema, delta, or frontier; independent valid
    off-grid points still retain their own calculated values. Invalid mask cells have
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
    x = _axis(baselines, field="baselines", allow_zero=False)
    y = _axis(dropout_rates, field="dropout_rates", allow_zero=True)
    for field, point in (("planned_point", planned_point), ("selected_point", selected_point)):
        if not isinstance(point, GridCoordinate):
            raise StatisticalInputError("Expected a GridCoordinate", field=field)
    planned, selected = planned_point, selected_point
    enrollment = fixed_enrollment.control
    points = tuple(tuple(_evaluate(enrollment, effect, GridCoordinate(baseline, dropout), alpha_value, target)
                         for baseline in x) for dropout in y)
    powers = tuple(tuple(point.power for point in row) for row in points)
    invalid = tuple(tuple(point.power is None for point in row) for row in points)
    below = tuple(tuple(point.below_target for point in row) for row in points)
    curve = tuple(_evaluate(enrollment, effect, GridCoordinate(baseline, selected.dropout), alpha_value, target)
                  for baseline in x)
    planned_result = _evaluate(enrollment, effect, planned, alpha_value, target)
    selected_result = _evaluate(enrollment, effect, selected, alpha_value, target)
    valid_powers = [value for row in powers for value in row if value is not None]
    invalid_count = sum(sum(row) for row in invalid)
    warnings = ["Expected-count approximation: floored expected retention is not a simulated or guaranteed retained count."]
    if invalid_count:
        warnings.append(f"{invalid_count} grid cells are unavailable due to invalid effect or insufficient expected retained counts.")
    if not valid_powers:
        warnings.append("All grid cells are invalid; worst-case power and analytic delta are unavailable and the frontier is empty.")
    if any(point.power is None for point in curve):
        warnings.append("Some selected-dropout power-curve points are unavailable.")
    for name, point in (("Planned", planned_result), ("Selected", selected_result)):
        if point.power is None:
            warnings.append(f"{name} point is unavailable: {point.invalid_reason}.")
    delta = None
    if valid_powers and planned_result.power is not None and selected_result.power is not None:
        delta = selected_result.power - planned_result.power
    return StressGridResult(
        grid_label=GRID_LABEL,
        fixed_enrollment=fixed_enrollment, x_baseline=x, y_dropout=y,
        power=powers, invalid_mask=invalid, below_target=below, target_power=target,
        planned_point=planned_result, selected_point=selected_result, analytic_delta=delta,
        power_curve=curve, frontier_points=_frontier(x, y, powers, target),
        worst_case_power=min(valid_powers) if valid_powers else None,
        invalid_cell_count=invalid_count, warnings=tuple(warnings),
    )
