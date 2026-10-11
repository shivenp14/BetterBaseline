"""Task #56 numerical and domain-boundary acceptance checks."""

from dataclasses import FrozenInstanceError
import math

import pytest

from app.statistics import Dropout, Effect, FixedEnrollment, StatisticalInputError, resolve_treatment_risk
from app.statistics import expected_retained_count


@pytest.mark.parametrize("enrolled,dropout,expected", [(903, 0, 903), (1004, .1, 903), (3, .5, 1), (1, .9, 0)])
def test_expected_retention_is_floored(enrolled, dropout, expected):
    assert expected_retained_count(enrolled, dropout) == expected


@pytest.mark.parametrize("enrolled,dropout,expected", [(1000, .8, 200), (100, .7, 30), (1000, .9, 100)])
def test_expected_retention_exact_decimal_integer_boundaries(enrolled, dropout, expected):
    assert expected_retained_count(enrolled, dropout) == expected


def test_expected_retention_preserves_fractional_counts_near_boundary():
    assert expected_retained_count(1000, math.nextafter(.8, 1)) == 199
    assert expected_retained_count(1000, math.nextafter(.8, 0)) == 200
    assert expected_retained_count(1000, .8001) == 199
    assert expected_retained_count(1000, .7999) == 200


def test_expected_retention_uses_exact_arithmetic_for_large_counts():
    assert expected_retained_count(10**30, .8) == 2 * 10**29


@pytest.mark.parametrize("enrolled,dropout", [(0, .1), (True, .1), (3.0, .1), (3, 1), (3, "10"), (3, float("nan"))])
def test_expected_retention_validates_inputs(enrolled, dropout):
    with pytest.raises(StatisticalInputError):
        expected_retained_count(enrolled, dropout)


@pytest.mark.parametrize("kind,value", [("relative_risk", .75), ("absolute_risk_reduction", .05)])
def test_reference_effect_conversion(kind, value):
    assert resolve_treatment_risk(.20, Effect(kind, value)) == pytest.approx(.15)


def test_rr_and_arr_diverge_under_baseline_shock():
    assert resolve_treatment_risk(.10, Effect("relative_risk", .75)) == pytest.approx(.075)
    assert resolve_treatment_risk(.10, Effect("absolute_risk_reduction", .05)) == pytest.approx(.05)


@pytest.mark.parametrize("control", [.04, .05])
def test_arr_invalid_at_or_below_reduction(control):
    with pytest.raises(StatisticalInputError) as caught:
        resolve_treatment_risk(control, Effect("absolute_risk_reduction", .05))
    assert caught.value.code == "INVALID_MODEL_INPUT"
    assert caught.value.field == "effect.value"


@pytest.mark.parametrize("value", [0, 1, -1, 20, float("nan"), float("inf"), -float("inf"), True, "0.2", None, 10**1000])
def test_invalid_control_risks(value):
    with pytest.raises(StatisticalInputError) as caught:
        resolve_treatment_risk(value, Effect("relative_risk", .75))
    assert caught.value.field == "control_event_rate"


@pytest.mark.parametrize("kind", ["relative_risk", "absolute_risk_reduction"])
@pytest.mark.parametrize("value", [0, 1, -0.1, 75, float("nan"), float("inf"), False, "0.75", None])
def test_invalid_effect_values(kind, value):
    with pytest.raises(StatisticalInputError):
        Effect(kind, value)


def test_unknown_effect_kind_and_untyped_effect_rejected():
    with pytest.raises(StatisticalInputError) as caught:
        Effect("odds_ratio", .75)
    assert caught.value.field == "effect.kind"
    with pytest.raises(StatisticalInputError):
        resolve_treatment_risk(.20, {"kind": "relative_risk", "value": .75})


def test_derived_probability_underflow_is_rejected():
    with pytest.raises(StatisticalInputError) as caught:
        resolve_treatment_risk(5e-324, Effect("relative_risk", .1))
    assert caught.value.field == "treatment_event_rate"


@pytest.mark.parametrize("value", [0, .1, .999])
def test_symmetric_dropout(value):
    dropout = Dropout(value, value)
    assert dropout.control == dropout.treatment == value


@pytest.mark.parametrize("arm", ["control", "treatment"])
@pytest.mark.parametrize("value", [-.1, 1, 10, float("nan"), float("inf"), True, "0.1", None])
def test_invalid_dropout(arm, value):
    values = {"control": .1, "treatment": .1, arm: value}
    with pytest.raises(StatisticalInputError) as caught:
        Dropout(**values)
    assert caught.value.field == f"dropout.{arm}"


def test_asymmetric_dropout_is_explicitly_unsupported():
    with pytest.raises(StatisticalInputError) as caught:
        Dropout(.1, .2)
    assert caught.value.code == "UNSUPPORTED_MODEL"
    assert caught.value.field == "dropout"


def test_equal_arm_enrollment():
    enrollment = FixedEnrollment(903, 903)
    assert enrollment.control == enrollment.treatment == 903
    with pytest.raises(FrozenInstanceError):
        enrollment.control = 1004


def test_unequal_arm_enrollment_is_explicitly_unsupported():
    with pytest.raises(StatisticalInputError) as caught:
        FixedEnrollment(903, 904)
    assert caught.value.code == "UNSUPPORTED_MODEL"
    assert caught.value.field == "enrolled_n"


@pytest.mark.parametrize("arm", ["control", "treatment"])
@pytest.mark.parametrize("value", [0, -1, 903.0, True, "903", None, float("inf"), float("nan")])
def test_invalid_enrollment(arm, value):
    values = {"control": 903, "treatment": 903, arm: value}
    with pytest.raises(StatisticalInputError) as caught:
        FixedEnrollment(**values)
    assert caught.value.field == f"enrolled_n.{arm}"


def test_inputs_are_immutable_and_conversion_preserves_effect():
    effect = Effect("relative_risk", .75)
    dropout = Dropout(.1, .1)
    resolve_treatment_risk(.2, effect)
    assert effect.value == .75
    with pytest.raises(FrozenInstanceError):
        effect.value = .5
    with pytest.raises(FrozenInstanceError):
        dropout.control = .2
