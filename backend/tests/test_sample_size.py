"""Task #57 analytic power and minimal equal-arm sample-size checks."""

import math

import pytest

from app.statistics import Dropout, StatisticalInputError
from app.statistics.analytic import (
    COHEN_H_NORMAL_METHOD,
    COHEN_H_NORMAL_VERSION,
    analytic_power,
)
from app.statistics.sample_size import (
    MAX_EVALUABLE_PER_ARM,
    minimum_sample_size,
)


def test_canonical_sample_size_fixture_and_dropout_inflation():
    result = minimum_sample_size(.20, .15, .80, .05, Dropout(.10, .10))
    assert result.evaluable_per_arm == 903
    assert result.enrolled_per_arm == 1004
    assert result.achieved_power >= .80
    assert result.power_at_previous_n < .80
    assert result.method == COHEN_H_NORMAL_METHOD
    assert result.method_version == COHEN_H_NORMAL_VERSION


def test_baseline_collapse_power_at_original_evaluable_n():
    result = analytic_power(.10, .075, 903, 903, .05)
    assert result.power == pytest.approx(.470, abs=.001)
    assert result.method == COHEN_H_NORMAL_METHOD
    assert result.method_version == COHEN_H_NORMAL_VERSION


def test_power_is_monotone_in_evaluable_n():
    powers = [analytic_power(.20, .15, n, n).power for n in (2, 10, 100, 500, 903, 2000)]
    assert powers == sorted(powers)


def test_smaller_effect_requires_more_evaluable_participants():
    strong = minimum_sample_size(.20, .10).evaluable_per_arm
    weaker = minimum_sample_size(.20, .15).evaluable_per_arm
    assert weaker > strong


def test_ceiling_is_tested_and_feasible_gap_after_power_of_two_is_searched():
    # 903 lies between the last doubled bracket (512) and this finite ceiling.
    result = minimum_sample_size(.20, .15, max_evaluable_per_arm=903)
    assert result.evaluable_per_arm == 903
    assert result.max_evaluable_per_arm == 903


def test_unmet_target_at_ceiling_is_infeasible():
    with pytest.raises(StatisticalInputError) as caught:
        minimum_sample_size(.20, .15, max_evaluable_per_arm=902)
    assert caught.value.code == "UNBOUNDED_OR_INFEASIBLE"
    assert caught.value.field == "max_evaluable_per_arm"


def test_null_effect_is_unbounded_or_infeasible():
    with pytest.raises(StatisticalInputError) as caught:
        minimum_sample_size(.20, .20)
    assert caught.value.code == "UNBOUNDED_OR_INFEASIBLE"


@pytest.mark.parametrize(
    "alpha,target",
    [(.05, .05), (0, .80), (1, .80), (.80, .80), (.05, 1), (.05, 0),
     (.05, float("nan")), (.05, float("inf")), (True, .80)],
)
def test_alpha_and_target_require_strict_finite_order(alpha, target):
    with pytest.raises(StatisticalInputError):
        minimum_sample_size(.20, .15, target_power=target, alpha=alpha)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_evaluable_per_arm": 1},
        {"max_evaluable_per_arm": 10.0},
        {"max_evaluable_per_arm": True},
        {"dropout": .10},
    ],
)
def test_invalid_search_configuration(kwargs):
    with pytest.raises(StatisticalInputError):
        minimum_sample_size(.20, .15, **kwargs)


def test_unequal_arm_sizes_and_unsupported_method_are_rejected():
    with pytest.raises(StatisticalInputError) as caught:
        analytic_power(.20, .15, 903, 904)
    assert caught.value.code == "UNSUPPORTED_MODEL"
    with pytest.raises(StatisticalInputError) as caught:
        analytic_power(.20, .15, 903, 903, method="pooled_z")
    assert caught.value.code == "UNSUPPORTED_MODEL"


@pytest.mark.parametrize(
    "p_control,p_treatment,n_control,n_treatment,alpha",
    [
        (0, .15, 903, 903, .05),
        (.20, 1, 903, 903, .05),
        (.20, .15, 0, 0, .05),
        (.20, .15, 903.0, 903.0, .05),
        (.20, .15, 903, 903, float("nan")),
        (.20, .15, 903, 903, 1),
    ],
)
def test_analytic_power_strict_validation(
    p_control, p_treatment, n_control, n_treatment, alpha,
):
    with pytest.raises(StatisticalInputError):
        analytic_power(p_control, p_treatment, n_control, n_treatment, alpha)


def test_extreme_valid_probabilities_are_not_clipped():
    result = analytic_power(1e-300, 1e-200, 903, 903)
    assert math.isfinite(result.power)
    assert result.effect_size_h > 0


def test_small_valid_alpha_does_not_round_upper_tail_to_one():
    result = analytic_power(.20, .15, 903, 903, alpha=1e-20)
    assert math.isfinite(result.power)
    assert result.power >= 0.0


def test_smallest_positive_alpha_has_finite_critical_value_and_correct_large_n_power():
    special = pytest.importorskip("scipy.special")
    alpha = math.nextafter(0.0, 1.0)
    z_alpha = -special.ndtri_exp(math.log(alpha) - math.log(2.0))
    h = 2.0 * math.asin(math.sqrt(.15)) - 2.0 * math.asin(math.sqrt(.20))
    mean = math.sqrt(1_000_000 / 2.0) * abs(h)
    expected = special.ndtr(mean - z_alpha) + special.ndtr(-mean - z_alpha)

    result = analytic_power(.20, .15, 1_000_000, 1_000_000, alpha=alpha)

    assert math.isfinite(z_alpha)
    assert result.power == pytest.approx(expected, abs=1e-15)
    assert result.power == 1.0


@pytest.mark.parametrize("multiple", [1, 3, 5, 7, 101])
def test_subnormal_alpha_solver_meets_target_at_oracle_boundary(multiple):
    special = pytest.importorskip("scipy.special")
    alpha = multiple * math.nextafter(0.0, 1.0)
    target = .80
    z_alpha = -special.ndtri_exp(math.log(alpha) - math.log(2.0))
    h = 2.0 * math.asin(math.sqrt(.15)) - 2.0 * math.asin(math.sqrt(.20))

    def oracle_power(n):
        mean = math.sqrt(n / 2.0) * abs(h)
        return special.ndtr(mean - z_alpha) + special.ndtr(-mean - z_alpha)

    result = minimum_sample_size(.20, .15, target_power=target, alpha=alpha)

    assert result.evaluable_per_arm > 2
    assert result.achieved_power == pytest.approx(oracle_power(result.evaluable_per_arm), abs=1e-14)
    assert oracle_power(result.evaluable_per_arm) >= target
    assert oracle_power(result.evaluable_per_arm - 1) < target


def test_independent_statsmodels_normal_ind_power_oracle():
    statsmodels_power = pytest.importorskip("statsmodels.stats.power")
    statsmodels_proportion = pytest.importorskip("statsmodels.stats.proportion")
    oracle = statsmodels_power.NormalIndPower()
    for p_control, p_treatment, n, alpha in (
        (.20, .15, 903, .05),
        (.10, .075, 903, .05),
        (.35, .20, 250, .025),
    ):
        observed = analytic_power(p_control, p_treatment, n, n, alpha).power
        h = statsmodels_proportion.proportion_effectsize(p_treatment, p_control)
        expected = oracle.power(
            effect_size=h,
            nobs1=n,
            alpha=alpha,
            ratio=1.0,
            alternative="two-sided",
        )
        assert observed == pytest.approx(expected, abs=1e-12)


def test_default_ceiling_is_finite_and_documented_in_result():
    assert MAX_EVALUABLE_PER_ARM == 1_000_000
    result = minimum_sample_size(.20, .15)
    assert result.max_evaluable_per_arm == MAX_EVALUABLE_PER_ARM
