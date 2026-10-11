"""A4: real analytical grid checks and contour topology regressions."""

from dataclasses import asdict, FrozenInstanceError
import json

import pytest

from app.statistics.analytic import analytic_power
from app.statistics.errors import StatisticalInputError
from app.statistics.inputs import Effect, FixedEnrollment, expected_retained_count
from app.statistics.stress_grid import GridCoordinate, stress_grid


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
        assert point.below_target == (point.power < .65)
        assert point.dropout == .07
        assert point.expected_evaluable_per_arm == n
        assert point.power == analytic_power(point.baseline, point.baseline * .75, n, n).power
    assert result.power_curve[1].power != result.power[0][1]
    assert result.power_curve[1].power != result.power[1][1]
    higher_target = grid(target_power=.95)
    assert [point.power for point in result.power_curve] == [point.power for point in higher_target.power_curve]
    assert [point.below_target for point in result.power_curve] != [point.below_target for point in higher_target.power_curve]
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
    assert result.power_curve[0].below_target is None
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
    assert result.analytic_delta is None


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
    ("dropout_rates", []), ("dropout_rates", [.1, 0]), ("dropout_rates", [0, 0]),
    ("dropout_rates", [-.1]), ("dropout_rates", [1]), ("dropout_rates", [float("inf")]),
])
def test_invalid_axes_are_rejected(field, values):
    with pytest.raises(StatisticalInputError):
        grid(**{field: values})


@pytest.mark.parametrize("overrides", [
    {"alpha": 0}, {"alpha": True}, {"target_power": .05}, {"target_power": 1},
    {"effect": {"kind": "relative_risk", "value": .75}}, {"fixed_enrollment": 903},
    {"planned_point": {"baseline": .2, "dropout": 0}},
])
def test_invalid_structural_inputs(overrides):
    with pytest.raises(StatisticalInputError):
        grid(**overrides)


@pytest.mark.parametrize("baseline,dropout", [(.2, 1), (float("inf"), 0), (20, 0), (.2, 10), (True, 0)])
def test_coordinates_validate_fraction_inputs_at_construction(baseline, dropout):
    with pytest.raises(StatisticalInputError):
        GridCoordinate(baseline, dropout)


def test_single_point_axes_have_no_frontier():
    assert grid(baselines=[.2], dropout_rates=[0]).frontier_points == ()


def test_statistical_core_accepts_axes_beyond_api_policy_limits():
    baselines = tuple(.05 + index * .003 for index in range(82))
    dropouts = tuple(index / 100 for index in range(62))
    result = grid(baselines=baselines, dropout_rates=dropouts)
    assert result.x_baseline == baselines
    assert result.y_dropout == dropouts
    assert len(result.power) == 62
    assert all(len(row) == 82 for row in result.power)


def test_arr_curve_uses_the_effect_at_each_baseline():
    result = grid(effect=Effect("absolute_risk_reduction", .05))
    n = expected_retained_count(1004, .07)
    for point in result.power_curve:
        assert point.power == analytic_power(point.baseline, point.baseline - .05, n, n).power
    assert result.power_curve != grid().power_curve


def test_real_frontier_stitches_across_multiple_rows():
    result = grid(baselines=[.1, .15, .2, .25, .3], dropout_rates=[0, .1, .2, .3], target_power=.7)
    assert len(result.frontier_points) == 1
    path = result.frontier_points[0].points
    assert {point.dropout for point in path} >= {0, .1, .2, .3}
    assert len(path) >= 4
    assert path == min(path, tuple(reversed(path)))


def test_disconnected_arr_frontiers_have_canonical_stable_order():
    args = dict(fixed_enrollment=FixedEnrollment(200, 200),
                effect=Effect("absolute_risk_reduction", .05),
                baselines=[.06, .1, .2, .4, .6, .8, .9, .95, .99],
                dropout_rates=[0, .1, .2], target_power=.3)
    result = grid(**args)
    paths = tuple(segment.points for segment in result.frontier_points)
    assert len(paths) == 2
    assert paths == tuple(sorted(paths))
    assert all(path == min(path, tuple(reversed(path))) for path in paths)
    assert max(point.baseline for point in paths[0]) < .2
    assert min(point.baseline for point in paths[1]) > .8
    assert result == grid(**args)


def test_invalid_corner_suppresses_a_bracketing_cell():
    result = grid(fixed_enrollment=FixedEnrollment(2, 2), baselines=[.1, .9],
                  dropout_rates=[0, .5], target_power=.07)
    assert result.below_target[0] == (True, False)
    assert result.invalid_mask[1] == (True, True)
    assert result.frontier_points == ()


def test_exact_target_vertex_emits_no_zero_length_path():
    target = grid().power[0][-1]
    result = grid(target_power=target)
    assert result.below_target[0][-1] is False
    assert result.frontier_points == ()


def test_exact_target_edge_uses_grid_vertices_without_duplicates():
    # These dropout values retain the same integer N, producing a target edge.
    base = grid(dropout_rates=[.0001, .0002], baselines=[.1, .2])
    result = grid(dropout_rates=[.0001, .0002], baselines=[.1, .2], target_power=base.power[1][1])
    assert len(result.frontier_points) == 1
    assert result.frontier_points[0].points == (GridCoordinate(.2, .0001), GridCoordinate(.2, .0002))


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
