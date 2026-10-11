import pytest
from app.statistics.effect import Effect
from app.statistics.sensitivity_grid import generate_stress_grid


def test_sensitivity_grid_nominal_envelope():
    """Verify that nominal parameters fall safely within the Assumption Safety Envelope."""
    # Frozen planned enrollment n=903 per arm, RR=0.75
    effect = Effect(kind="relative_risk", value=0.75)
    result = generate_stress_grid(
        fixed_n_enrolled_per_arm=903,
        effect=effect,
        target_power=0.80,
        alpha=0.05,
        p_control_min=0.05,
        p_control_max=0.30,
        p_control_count=6,
        dropout_min=0.0,
        dropout_max=0.30,
        dropout_count=4,
    )

    assert result.fixed_n_enrolled_per_arm == 903
    assert len(result.grid) == 6
    assert len(result.grid[0]) == 4

    # High baseline (e.g. p_c = 0.30) with 0 dropout should be well within safety envelope
    highest_p_c_row = result.grid[-1]
    assert highest_p_c_row[0].is_safe is True
    assert highest_p_c_row[0].power > 0.80

    # Low baseline (e.g. p_c = 0.05) should collapse outside safety envelope
    lowest_p_c_row = result.grid[0]
    assert lowest_p_c_row[0].is_safe is False
    assert lowest_p_c_row[0].power < 0.50


def test_sensitivity_grid_arr_invalid_scenarios():
    """Verify that ARR mode flags cells where ARR >= p_control as invalid without throwing."""
    effect = Effect(kind="absolute_risk_reduction", value=0.08)
    result = generate_stress_grid(
        fixed_n_enrolled_per_arm=500,
        effect=effect,
        target_power=0.80,
        p_control_min=0.05,
        p_control_max=0.20,
        p_control_count=4,
    )

    # For p_control = 0.05, ARR = 0.08 is impossible (p_t would be negative)
    p_c_005_row = result.grid[0]
    assert p_c_005_row[0].is_valid is False
    assert p_c_005_row[0].power is None
    assert p_c_005_row[0].is_safe is False
    assert "ARR must be in (0, p_control)" in (p_c_005_row[0].reason_invalid or "")

    # For higher p_control (e.g. 0.20), ARR = 0.08 is valid
    p_c_high_row = result.grid[-1]
    assert p_c_high_row[0].is_valid is True
    assert p_c_high_row[0].power is not None
