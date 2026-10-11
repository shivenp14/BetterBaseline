import pytest
from app.statistics.monte_carlo import SimulationParams, simulate_binary_trials


def test_monte_carlo_nominal_scenario():
    """Simulate 10,000 trials under nominal planned design (n=903, p_c=0.20, p_t=0.15)."""
    params = SimulationParams(
        n_enrolled_control=903,
        n_enrolled_treatment=903,
        p_control=0.20,
        p_treatment=0.15,
        dropout_control=0.0,
        dropout_treatment=0.0,
        alpha=0.05,
        replications=10_000,
        seed=42,
    )
    result = simulate_binary_trials(params)

    # Power should be close to 80% (within 3 * MCSE)
    assert result.power_two_sided == pytest.approx(0.80, abs=0.02)
    assert result.power_favorable == pytest.approx(result.power_two_sided, abs=0.005)
    assert result.mcse_two_sided < 0.005
    assert result.invalid_trials_count == 0


def test_monte_carlo_baseline_collapse():
    """Simulate baseline collapse (n=903, p_c=0.10, p_t=0.075). Power should collapse to ~47%."""
    params = SimulationParams(
        n_enrolled_control=903,
        n_enrolled_treatment=903,
        p_control=0.10,
        p_treatment=0.075,
        dropout_control=0.0,
        dropout_treatment=0.0,
        alpha=0.05,
        replications=10_000,
        seed=42,
    )
    result = simulate_binary_trials(params)

    assert result.power_two_sided == pytest.approx(0.47, abs=0.02)
    assert result.power_favorable == pytest.approx(0.47, abs=0.02)
    assert result.invalid_trials_count == 0


def test_monte_carlo_null_hypothesis_type_one_error():
    """Under true null (p_c == p_t = 0.20), rejection rate should be approximately alpha (0.05)."""
    params = SimulationParams(
        n_enrolled_control=500,
        n_enrolled_treatment=500,
        p_control=0.20,
        p_treatment=0.20,
        alpha=0.05,
        replications=10_000,
        seed=123,
    )
    result = simulate_binary_trials(params)

    # Two-sided empirical false positive rate should be around 0.05
    assert result.power_two_sided == pytest.approx(0.05, abs=0.01)
    # Favorable direction under symmetric null is approximately alpha / 2 = 0.025
    assert result.power_favorable == pytest.approx(0.025, abs=0.008)


def test_monte_carlo_with_dropout():
    """Test dropout mechanism reducing retained sample size."""
    params = SimulationParams(
        n_enrolled_control=1000,
        n_enrolled_treatment=1000,
        p_control=0.20,
        p_treatment=0.15,
        dropout_control=0.10,
        dropout_treatment=0.10,
        alpha=0.05,
        replications=2_000,
        seed=999,
    )
    result = simulate_binary_trials(params)

    # Expected retained is around 900 per arm
    assert result.mean_retained_control == pytest.approx(900.0, abs=10.0)
    assert result.mean_retained_treatment == pytest.approx(900.0, abs=10.0)
    assert result.invalid_trials_count == 0
