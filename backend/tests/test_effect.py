import pytest
from app.statistics.effect import Effect, calculate_treatment_risk


def test_relative_risk_calculation():
    # Canonical preset: p_control = 0.20, RR = 0.75 -> p_treatment = 0.15
    effect = Effect(kind="relative_risk", value=0.75)
    p_t = calculate_treatment_risk(0.20, effect)
    assert p_t == pytest.approx(0.15)


def test_relative_risk_shock():
    # Shock scenario: p_control drops to 0.10, RR remains 0.75 -> p_treatment = 0.075
    effect = Effect(kind="relative_risk", value=0.75)
    p_t = calculate_treatment_risk(0.10, effect)
    assert p_t == pytest.approx(0.075)


def test_absolute_risk_reduction():
    # ARR: p_control = 0.20, ARR = 0.05 -> p_treatment = 0.15
    effect = Effect(kind="absolute_risk_reduction", value=0.05)
    p_t = calculate_treatment_risk(0.20, effect)
    assert p_t == pytest.approx(0.15)


def test_invalid_p_control():
    effect = Effect(kind="relative_risk", value=0.75)
    with pytest.raises(ValueError, match="p_control must be in"):
        calculate_treatment_risk(0.0, effect)
    with pytest.raises(ValueError, match="p_control must be in"):
        calculate_treatment_risk(1.0, effect)
    with pytest.raises(ValueError, match="p_control must be in"):
        calculate_treatment_risk(-0.1, effect)


def test_invalid_relative_risk():
    with pytest.raises(ValueError, match="RR must be in"):
        calculate_treatment_risk(0.20, Effect(kind="relative_risk", value=1.0))
    with pytest.raises(ValueError, match="RR must be in"):
        calculate_treatment_risk(0.20, Effect(kind="relative_risk", value=0.0))
    with pytest.raises(ValueError, match="RR must be in"):
        calculate_treatment_risk(0.20, Effect(kind="relative_risk", value=-0.5))


def test_invalid_arr_greater_than_control():
    # In ARR mode, ARR cannot equal or exceed p_control (which would yield p_t <= 0)
    effect = Effect(kind="absolute_risk_reduction", value=0.15)
    with pytest.raises(ValueError, match="ARR must be in"):
        calculate_treatment_risk(0.10, effect)
