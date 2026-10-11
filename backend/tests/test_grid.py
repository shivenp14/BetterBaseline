"""A4: real analytical grid checks and contour topology regressions."""

from dataclasses import asdict, FrozenInstanceError
import json
import math
from unittest.mock import patch

import pytest

from app.statistics.analytic import analytic_power, COHEN_H_NORMAL_METHOD, COHEN_H_NORMAL_VERSION
from app.statistics.errors import StatisticalInputError
from app.statistics.inputs import Effect, FixedEnrollment, expected_retained_count
from app.statistics.stress_grid import GridCoordinate, _frontier, stress_grid


def grid(**overrides):
    args = dict(fixed_enrollment=FixedEnrollment(1004, 1004), effect=Effect("relative_risk", .75),
                baselines=[.1, .2, .3], dropout_rates=[0, .1],
                planned_point=GridCoordinate(.2, .1), selected_point=GridCoordinate(.1, .07))
    args.update(overrides)
    return stress_grid(**args)


def test_shape_orientation_and_real_scalar_agreement():
    result = grid()
    assert len(result.power) == 2
    assert all(len(row) == 3 for row in result.power)
    for row, dropout in enumerate(result.y_dropout):
        for column, baseline in enumerate(result.x_baseline):
            n = expected_retained_count(1004, dropout)
            assert result.power[row][column] == analytic_power(baseline, baseline * .75, n, n).power
            assert result.invalid_mask[row][column] is False
            assert result.below_target[row][column] == (result.power[row][column] < .8)
    assert result.worst_case_power == min(value for row in result.power for value in row)
    assert result.method == COHEN_H_NORMAL_METHOD
    assert result.method_version == COHEN_H_NORMAL_VERSION
    assert result.grid_label == "expected_count_approximation"


def test_exact_decimal_floor_boundary_and_fractional_floor():
    result = grid(fixed_enrollment=FixedEnrollment(1000, 1000), dropout_rates=[.8],
                  selected_point=GridCoordinate(.2, .8001))
    assert result.power[0][1] == analytic_power(.2, .15, 200, 200).power
    assert result.selected_point.expected_evaluable_per_arm == 199
    assert result.power_curve[1].expected_evaluable_per_arm == 199


def test_curve_uses_exact_selected_dropout_and_target():
    result = grid(target_power=.65)
    for point in result.power_curve:
        n = expected_retained_count(1004, .07)
        assert point.dropout == .07
        assert point.expected_evaluable_per_arm == n
        assert point.power == analytic_power(point.baseline, point.baseline * .75, n, n).power
    assert result.power_curve[1].power != result.power[0][1]
    assert result.power_curve[1].power != result.power[1][1]
    assert result.target_power == .65
    assert result.frontier_points != grid(target_power=.8).frontier_points


def test_points_are_directly_evaluated_off_grid_with_frozen_enrollment():
    enrollment = FixedEnrollment(903, 903)
    result = grid(fixed_enrollment=enrollment, planned_point=GridCoordinate(.2, 0),
                  selected_point=GridCoordinate(.07, .17))
    assert result.fixed_enrollment is enrollment
    assert result.planned_point.power >= .8
    n = expected_retained_count(903, .17)
    assert result.selected_point.power == analytic_power(.07, .07 * .75, n, n).power
    assert result.analytic_delta == result.selected_point.power - result.planned_point.power
    with pytest.raises(FrozenInstanceError):
        result.target_power = .9
    assert enrollment == FixedEnrollment(903, 903)


def test_invalid_arr_is_null_with_matching_mask_and_no_contour_bridge():
    result = grid(effect=Effect("absolute_risk_reduction", .05), baselines=[.04, .05, .1], target_power=.5)
    assert result.invalid_cell_count == 4
    for row in range(2):
        assert result.power[row][:2] == (None, None)
        assert result.invalid_mask[row] == (True, True, False)
        assert result.below_target[row][:2] == (None, None)
    assert result.frontier_points == ()
    assert result.power_curve[0].invalid_reason == "INVALID_EFFECT_AT_BASELINE"
    n = expected_retained_count(1004, .07)
    assert result.power_curve[2].power == analytic_power(.1, .05, n, n).power


def test_all_invalid_domain_has_null_summary_and_warning():
    result = grid(effect=Effect("absolute_risk_reduction", .4))
    assert result.worst_case_power is None
    assert result.invalid_cell_count == 6
    assert result.frontier_points == ()
    assert result.analytic_delta is None
    assert result.selected_point.power is None
    assert any("All grid cells are invalid" in warning for warning in result.warnings)
    assert json.loads(json.dumps(asdict(result), allow_nan=False))["worst_case_power"] is None


def test_all_invalid_grid_keeps_valid_independent_off_grid_points():
    result = grid(effect=Effect("absolute_risk_reduction", .05), baselines=[.03, .04])
    assert result.worst_case_power is None
    assert result.planned_point.power is not None
    assert result.selected_point.power is not None


@pytest.mark.parametrize("enrollment", [1, 2])
def test_insufficient_retained_counts_are_unavailable(enrollment):
    result = grid(fixed_enrollment=FixedEnrollment(enrollment, enrollment), dropout_rates=[.9])
    assert result.power == ((None, None, None),)
    assert result.invalid_cell_count == 3


def test_invalid_selected_point_has_no_delta_without_invalidating_grid():
    result = grid(effect=Effect("absolute_risk_reduction", .05), selected_point=GridCoordinate(.04, 0))
    assert result.invalid_cell_count == 0
    assert result.selected_point.power is None
    assert result.analytic_delta is None
    assert any("Selected point is unavailable" in warning for warning in result.warnings)


@pytest.mark.parametrize("enrollment,target", [(100000, .1), (10, .99)])
def test_all_above_or_all_below_has_no_contour(enrollment, target):
    result = grid(fixed_enrollment=FixedEnrollment(enrollment, enrollment), target_power=target)
    assert result.frontier_points == ()
    assert result.worst_case_power is not None
    masks = [cell for row in result.below_target for cell in row]
    assert all(cell == (enrollment == 10) for cell in masks)


def test_repeatability_and_strict_finite_json():
    assert json.dumps(asdict(grid()), allow_nan=False, sort_keys=True) == json.dumps(asdict(grid()), allow_nan=False, sort_keys=True)


@pytest.mark.parametrize("field,values", [
    ("baselines", []), ("baselines", [.2, .1]), ("baselines", [.1, .1]),
    ("baselines", [0]), ("baselines", [1]), ("baselines", [float("nan")]),
    ("baselines", [True]), ("baselines", "0.1"),
    ("baselines", [(index + 1) / 100 for index in range(82)]),
    ("dropout_rates", []), ("dropout_rates", [.1, 0]), ("dropout_rates", [0, 0]),
    ("dropout_rates", [-.1]), ("dropout_rates", [1]), ("dropout_rates", [float("inf")]),
    ("dropout_rates", [index / 100 for index in range(62)]),
])
def test_invalid_axes_fail_before_computation(field, values):
    with patch("app.statistics.stress_grid.analytic_power") as compute:
        with pytest.raises(StatisticalInputError):
            grid(**{field: values})
        compute.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"alpha": 0}, {"alpha": True}, {"target_power": .05}, {"target_power": 1},
    {"effect": {"kind": "relative_risk", "value": .75}}, {"fixed_enrollment": 903},
    {"planned_point": {"baseline": .2, "dropout": 0}},
    {"selected_point": GridCoordinate(.2, 1)}, {"planned_point": GridCoordinate(math.inf, 0)},
])
def test_invalid_structural_inputs(overrides):
    with pytest.raises(StatisticalInputError):
        grid(**overrides)


def test_unexpected_analytic_failures_are_not_masked_as_invalid_cells():
    with patch("app.statistics.stress_grid.analytic_power", side_effect=RuntimeError("broken engine")):
        with pytest.raises(RuntimeError, match="broken engine"):
            grid()


def test_nonfinite_analytic_results_fail_explicitly():
    with patch("app.statistics.stress_grid.analytic_power") as compute:
        compute.return_value.power = math.nan
        with pytest.raises(ArithmeticError):
            grid()


def test_single_point_axes_have_no_frontier():
    assert grid(baselines=[.2], dropout_rates=[0]).frontier_points == ()


def test_full_supported_axis_dimensions_and_stable_order():
    baselines = tuple(.05 + index * .003 for index in range(81))
    dropouts = tuple(index / 100 for index in range(61))
    result = grid(baselines=baselines, dropout_rates=dropouts)
    assert result.x_baseline == baselines
    assert result.y_dropout == dropouts
    assert len(result.power) == 61
    assert all(len(row) == 81 for row in result.power)


def test_arr_curve_uses_the_effect_at_each_baseline():
    result = grid(effect=Effect("absolute_risk_reduction", .05))
    n = expected_retained_count(1004, .07)
    for point in result.power_curve:
        assert point.power == analytic_power(point.baseline, point.baseline - .05, n, n).power
    assert result.power_curve != grid().power_curve


def test_cell_limit_is_enforced_before_core_allocation():
    with patch("app.statistics.stress_grid.MAX_GRID_CELLS", 5), patch("app.statistics.stress_grid.analytic_power") as compute:
        with pytest.raises(StatisticalInputError) as error:
            grid()
        assert error.value.field == "grid"
        compute.assert_not_called()


def test_frontier_stitches_adjacent_valid_cells_into_one_path():
    segments = _frontier((.1, .2, .3), (0, .1), ((.2, .5, .8), (.2, .5, .8)), .6)
    assert len(segments) == 1
    assert {point.dropout for point in segments[0].points} == {0, .1}
    assert all(point.baseline == pytest.approx(.2 + .1 / 3) for point in segments[0].points)
    # A horizontal contour spanning multiple cells must share exact node keys.
    segments = _frontier((.1, .2, .3), (0, .1), ((.2, .2, .2), (.8, .8, .8)), .5)
    assert len(segments) == 1
    assert len(segments[0].points) == 3
    assert all(point.dropout == pytest.approx(.05) for point in segments[0].points)


def test_invalid_boundary_does_not_connect_disconnected_contours():
    x, y = (.1, .2, .3, .4, .5), (0, .1)
    powers = ((.2, .2, None, .2, .2), (.8, .8, None, .8, .8))
    segments = _frontier(x, y, powers, .5)
    assert len(segments) == 2
    for segment in segments:
        baselines = [point.baseline for point in segment.points]
        assert max(baselines) <= .2 or min(baselines) >= .4


def test_even_one_invalid_corner_suppresses_cell_contour():
    assert _frontier((.1, .2), (0, .1), ((.2, .8), (.8, None)), .5) == ()


def test_exact_target_plateau_and_isolated_vertex_emit_no_zero_length_paths():
    assert _frontier((.1, .2), (0, .1), ((.5, .5), (.5, .5)), .5) == ()
    assert _frontier((.1, .2), (0, .1), ((.5, .2), (.2, .2)), .5) == ()


def test_exact_target_edge_is_deduplicated_and_bounded():
    segments = _frontier((.1, .2, .3), (0, .1), ((.2, .5, .2), (.2, .5, .2)), .5)
    assert len(segments) == 1
    assert set(segments[0].points) == {GridCoordinate(.2, 0), GridCoordinate(.2, .1)}


@pytest.mark.parametrize("powers", [((.2, .8), (.8, .2)), ((.8, .2), (.2, .8))])
def test_saddle_cell_has_two_deterministic_unjoined_segments(powers):
    segments = _frontier((.1, .2), (0, .1), powers, .5)
    assert len(segments) == 2
    assert segments == _frontier((.1, .2), (0, .1), powers, .5)
    assert all(len(segment.points) == 2 for segment in segments)


def test_closed_contour_repeats_first_point():
    segments = _frontier((.1, .2, .3), (0, .1, .2), ((.2, .2, .2), (.2, .8, .2), (.2, .2, .2)), .5)
    assert len(segments) == 1
    assert len(segments[0].points) == 5
    assert segments[0].points[0] == segments[0].points[-1]


def test_real_frontier_nodes_bracket_requested_target_on_valid_grid_edges():
    result = grid(baselines=[.05, .1, .15, .2, .25, .3], dropout_rates=[0, .1, .2, .3], target_power=.7)
    assert result.frontier_points
    for segment in result.frontier_points:
        for point in segment.points:
            matches = []
            for row in range(len(result.y_dropout)):
                for column in range(len(result.x_baseline)):
                    for r2, c2 in ((row + 1, column), (row, column + 1)):
                        if r2 >= len(result.y_dropout) or c2 >= len(result.x_baseline):
                            continue
                        a, b = result.power[row][column], result.power[r2][c2]
                        if a is None or b is None or a == b or not min(a, b) <= .7 <= max(a, b):
                            continue
                        fraction = (.7 - a) / (b - a)
                        expected_x = result.x_baseline[column] + fraction * (result.x_baseline[c2] - result.x_baseline[column])
                        expected_y = result.y_dropout[row] + fraction * (result.y_dropout[r2] - result.y_dropout[row])
                        matches.append(abs(point.baseline - expected_x) < 1e-12 and abs(point.dropout - expected_y) < 1e-12)
            assert any(matches)
