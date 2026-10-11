import pytest
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

from app.statistics.power_solver import (
    analytic_power,
    cohen_h,
    solve_evaluable_sample_size,
    calculate_trial_design,
)


def test_cohen_h_matches_statsmodels():
    p_c, p_t = 0.20, 0.15
    expected_h = proportion_effectsize(p_t, p_c)
    calculated_h = cohen_h(p_c, p_t)
    assert abs(calculated_h) == pytest.approx(abs(expected_h), abs=1e-7)


def test_canonical_903_sample_size_benchmark():
    """Verify that canonical planning parameters yield exactly 903 evaluable subjects/arm."""
    p_c = 0.20
    p_t = 0.15
    alpha = 0.05
    target_power = 0.80

    n_eval = solve_evaluable_sample_size(
        p_control=p_c,
        p_treatment=p_t,
        target_power=target_power,
        alpha=alpha,
    )
    assert n_eval == 903

    # Power at n=903 must meet or exceed target
    power_903 = analytic_power(p_c, p_t, n_per_arm=903, alpha=alpha)
    assert power_903 >= 0.80
    assert power_903 == pytest.approx(0.8005, abs=1e-3)

    # Power at n=902 must be strictly below target
    power_902 = analytic_power(p_c, p_t, n_per_arm=902, alpha=alpha)
    assert power_902 < 0.80


def test_baseline_collapse_power_drop_to_47_percent():
    """Verify that keeping n=903 frozen while p_control drops to 0.10 plunges power to ~47%."""
    # Under fixed RR = 0.75:
    # Planned: p_c = 0.20, p_t = 0.15 -> n=903 per arm gives ~80% power
    # Collapse: p_c = 0.10, p_t = 0.075 -> conditional power at frozen n=903
    p_c_shock = 0.10
    p_t_shock = 0.075
    alpha = 0.05

    power_shock = analytic_power(p_c_shock, p_t_shock, n_per_arm=903, alpha=alpha)
    # The specification explicitly mandates approximately 47% (0.470)
    assert power_shock == pytest.approx(0.470, abs=0.005)


def test_statsmodels_normal_ind_power_cross_validation():
    """Cross-verify analytic_power directly against statsmodels NormalIndPower."""
    p_c = 0.20
    p_t = 0.15
    alpha = 0.05
    n = 903

    h = proportion_effectsize(p_t, p_c)
    sm_power = NormalIndPower().power(
        effect_size=abs(h),
        nobs1=n,
        alpha=alpha,
        ratio=1.0,
        alternative="two-sided",
    )

    our_power = analytic_power(p_c, p_t, n_per_arm=n, alpha=alpha)
    assert our_power == pytest.approx(sm_power, abs=1e-5)


def test_trial_design_with_dropout_inflation():
    """Verify trial design calculations with 10% dropout."""
    result = calculate_trial_design(
        p_control=0.20,
        p_treatment=0.15,
        target_power=0.80,
        alpha=0.05,
        dropout_control=0.10,
        dropout_treatment=0.10,
    )
    # ceil(903 / 0.9) = 1004
    assert result.n_evaluable_per_arm == 903
    assert result.n_enrolled_per_arm == 1004
    assert result.total_enrolled == 2008
    assert result.nominal_power >= 0.80
