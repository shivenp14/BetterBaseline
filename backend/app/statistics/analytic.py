"""Analytic power for the canonical equal-arm Cohen's-h normal method."""

from dataclasses import dataclass
import math
import sys
from statistics import NormalDist

from .errors import StatisticalInputError
from .inputs import FixedEnrollment
from .validation import finite_number, probability

COHEN_H_NORMAL_METHOD = "cohen_h_normal"
COHEN_H_NORMAL_VERSION = "1.0.0"
_STANDARD_NORMAL = NormalDist()
_LOG_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def _log_normal_survival(z: float) -> float:
    """Return log(P(Z > z)) without underflow for large positive z."""
    if z < 8.0:
        return math.log(0.5 * math.erfc(z / math.sqrt(2.0)))

    # Continued fraction for the Mills ratio Q(z) / phi(z). At z >= 8,
    # this converges quickly and avoids evaluating an underflowing erfc.
    denominator = z
    for order in range(128, 0, -1):
        denominator = z + order / denominator
    log_mills_ratio = -math.log(denominator)
    return -0.5 * z * z - _LOG_SQRT_2PI + log_mills_ratio


def _normal_isf_from_log_probability(log_probability: float) -> float:
    """Invert the normal survival function from a finite log probability."""
    lower = 0.0
    upper = math.sqrt(-2.0 * log_probability)
    # The upper bound is above the root because the normal tail is smaller
    # than exp(-z**2 / 2). Bisection remains stable even for subnormal tails.
    for _ in range(100):
        middle = (lower + upper) / 2.0
        if _log_normal_survival(middle) > log_probability:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


@dataclass(frozen=True)
class AnalyticPowerResult:
    """A calculated power value and its local statistical provenance."""

    power: float
    method: str
    method_version: str
    effect_size_h: float
    p_control: float
    p_treatment: float
    n_per_arm: int
    alpha: float


def cohen_h(p_control: float, p_treatment: float) -> float:
    """Return signed Cohen's h for two independent proportions."""
    control = probability(p_control, field="p_control")
    treatment = probability(p_treatment, field="p_treatment")
    return 2.0 * math.asin(math.sqrt(treatment)) - 2.0 * math.asin(math.sqrt(control))


def analytic_power(
    p_control: float,
    p_treatment: float,
    n_control_evaluable: int,
    n_treatment_evaluable: int,
    alpha: float = 0.05,
    *,
    method: str = COHEN_H_NORMAL_METHOD,
) -> AnalyticPowerResult:
    """Calculate two-sided Cohen's-h normal-approximation power.

    The MVP supports equal evaluable arm sizes only. `method` is explicit to
    make unsupported method requests fail instead of silently changing the
    scientific calculation.
    """
    if method != COHEN_H_NORMAL_METHOD:
        raise StatisticalInputError(
            "Unsupported analytic power method", field="method", code="UNSUPPORTED_MODEL",
        )
    control = probability(p_control, field="p_control")
    treatment = probability(p_treatment, field="p_treatment")
    enrollment = FixedEnrollment(n_control_evaluable, n_treatment_evaluable)
    alpha_value = finite_number(alpha, field="alpha")
    if not 0.0 < alpha_value < 1.0:
        raise StatisticalInputError("Alpha must be in (0, 1)", field="alpha")

    h = cohen_h(control, treatment)
    lower_tail = alpha_value / 2.0
    # Use the symmetric lower-tail quantile to avoid rounding 1-alpha/2 to
    # exactly 1.0. Subnormal tails lose relative precision when halving alpha,
    # so invert their log probability with the stable tail calculation.
    z_alpha = (
        _normal_isf_from_log_probability(math.log(alpha_value) - math.log(2.0))
        if lower_tail < sys.float_info.min
        else -_STANDARD_NORMAL.inv_cdf(lower_tail)
    )
    noncentral_mean = math.sqrt(enrollment.control / 2.0) * abs(h)
    power = _STANDARD_NORMAL.cdf(noncentral_mean - z_alpha) + _STANDARD_NORMAL.cdf(
        -noncentral_mean - z_alpha
    )
    return AnalyticPowerResult(
        power=power,
        method=COHEN_H_NORMAL_METHOD,
        method_version=COHEN_H_NORMAL_VERSION,
        effect_size_h=h,
        p_control=control,
        p_treatment=treatment,
        n_per_arm=enrollment.control,
        alpha=alpha_value,
    )
