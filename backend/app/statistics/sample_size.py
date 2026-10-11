"""Minimal equal-arm evaluable sample size and dropout enrollment inflation."""

from dataclasses import dataclass
from decimal import Decimal
import math

from .analytic import (
    COHEN_H_NORMAL_METHOD,
    COHEN_H_NORMAL_VERSION,
    AnalyticPowerResult,
    analytic_power,
)
from .errors import StatisticalInputError
from .inputs import Dropout
from .validation import finite_number, probability

# Public default ceiling. Callers may choose a different finite ceiling per search.
MAX_EVALUABLE_PER_ARM = 1_000_000


@dataclass(frozen=True)
class SampleSizeResult:
    """Per-arm minimum and enrollment with enough information to audit it."""

    evaluable_per_arm: int
    enrolled_per_arm: int
    achieved_power: float
    power_at_previous_n: float | None
    p_control: float
    p_treatment: float
    alpha: float
    target_power: float
    dropout: float
    max_evaluable_per_arm: int
    method: str
    method_version: str


def _positive_integer_at_least_two(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise StatisticalInputError(
            "Expected an integer of at least 2", field=field,
        )
    return value


def minimum_sample_size(
    p_control: float,
    p_treatment: float,
    target_power: float = 0.80,
    alpha: float = 0.05,
    dropout: Dropout = Dropout(0.0, 0.0),
    *,
    max_evaluable_per_arm: int = MAX_EVALUABLE_PER_ARM,
) -> SampleSizeResult:
    """Find the smallest equal evaluable N/arm meeting target power.

    Search starts at n=2 and doubles its upper bracket, clamping and testing
    the configured finite ceiling. If that ceiling is feasible, binary search
    covers every integer between the last failed bracket and that ceiling.
    """
    control = probability(p_control, field="p_control")
    treatment = probability(p_treatment, field="p_treatment")
    alpha_value = finite_number(alpha, field="alpha")
    target = finite_number(target_power, field="target_power")
    if not 0.0 < alpha_value < 1.0:
        raise StatisticalInputError("Alpha must be in (0, 1)", field="alpha")
    if not 0.0 < target < 1.0:
        raise StatisticalInputError("Target power must be in (0, 1)", field="target_power")
    if not alpha_value < target:
        raise StatisticalInputError(
            "Target power must be greater than alpha", field="target_power",
        )
    maximum = _positive_integer_at_least_two(
        max_evaluable_per_arm, field="max_evaluable_per_arm",
    )
    if not isinstance(dropout, Dropout):
        raise StatisticalInputError("Expected a symmetric Dropout input", field="dropout")

    if control == treatment:
        raise StatisticalInputError(
            "A null effect cannot reach target power above alpha at finite N",
            field="p_treatment",
            code="UNBOUNDED_OR_INFEASIBLE",
        )

    def power_at(n: int) -> AnalyticPowerResult:
        return analytic_power(control, treatment, n, n, alpha_value)

    first = power_at(2)
    if first.power >= target:
        n = 2
        achieved = first.power
        previous_power = None
    else:
        failed_n = 2
        upper = 2
        bracketed = False
        while upper < maximum:
            candidate = min(upper * 2, maximum)
            candidate_power = power_at(candidate).power
            if candidate_power >= target:
                lower, upper = failed_n + 1, candidate
                bracketed = True
                break
            failed_n = candidate
            upper = candidate

        if not bracketed:
            raise StatisticalInputError(
                "Target power is not reached at the configured maximum evaluable N",
                field="max_evaluable_per_arm",
                code="UNBOUNDED_OR_INFEASIBLE",
            )

        while lower < upper:
            middle = (lower + upper) // 2
            if power_at(middle).power >= target:
                upper = middle
            else:
                lower = middle + 1
        n = lower
        achieved = power_at(n).power
        previous_power = power_at(n - 1).power

    num, den = Decimal(str(dropout.control)).as_integer_ratio()
    ret_num = den - num
    enrolled = (n * den + ret_num - 1) // ret_num
    return SampleSizeResult(
        evaluable_per_arm=n,
        enrolled_per_arm=enrolled,
        achieved_power=achieved,
        power_at_previous_n=previous_power,
        p_control=control,
        p_treatment=treatment,
        alpha=alpha_value,
        target_power=target,
        dropout=dropout.control,
        max_evaluable_per_arm=maximum,
        method=COHEN_H_NORMAL_METHOD,
        method_version=COHEN_H_NORMAL_VERSION,
    )
