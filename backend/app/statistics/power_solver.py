"""Analytical power calculation and sample size solving for two-arm clinical trials.

Implements the canonical Cohen's h / arcsine normal approximation:
  h = 2 * arcsin(sqrt(p_treatment)) - 2 * arcsin(sqrt(p_control))
  Power_h(n) = Phi(sqrt(n/2)*|h| - z_{1-alpha/2}) + Phi(-sqrt(n/2)*|h| - z_{1-alpha/2})

Provides:
- analytic_power: Evaluates power for given evaluable sample size.
- solve_evaluable_sample_size: Integer search for minimum evaluable sample size meeting target power.
- calculate_enrolled_sample_size: Computes required enrollment adjusting for arm-specific dropout.
"""

import math
from typing import NamedTuple
from scipy.stats import norm


class SampleSizeResult(NamedTuple):
    n_evaluable_per_arm: int
    total_evaluable: int
    n_enrolled_per_arm: int
    total_enrolled: int
    nominal_power: float
    effect_size_h: float


def cohen_h(p_control: float, p_treatment: float) -> float:
    """Compute Cohen's h effect size for two proportions."""
    return 2.0 * math.asin(math.sqrt(p_treatment)) - 2.0 * math.asin(math.sqrt(p_control))


def analytic_power(
    p_control: float,
    p_treatment: float,
    n_per_arm: int,
    alpha: float = 0.05,
) -> float:
    """Calculate analytical statistical power using the Cohen's h arcsine approximation.

    Args:
        p_control: Event rate in control arm in (0, 1).
        p_treatment: Event rate in treatment arm in (0, 1).
        n_per_arm: Evaluable sample size per arm (must be >= 2).
        alpha: Two-sided significance level (default: 0.05).

    Returns:
        Conditional statistical power in [0, 1].
    """
    if n_per_arm < 2:
        return 0.0
    if p_control <= 0.0 or p_control >= 1.0 or p_treatment <= 0.0 or p_treatment >= 1.0:
        raise ValueError("Probabilities must be strictly between 0 and 1.")
    if p_control == p_treatment:
        return alpha

    h = abs(cohen_h(p_control, p_treatment))
    z_alpha = norm.ppf(1.0 - alpha / 2.0)
    term = math.sqrt(n_per_arm / 2.0) * h

    # Two-sided normal power formula:
    # Power = Phi(term - z_{1-alpha/2}) + Phi(-term - z_{1-alpha/2})
    power = float(norm.cdf(term - z_alpha) + norm.cdf(-term - z_alpha))
    return min(max(power, 0.0), 1.0)


def solve_evaluable_sample_size(
    p_control: float,
    p_treatment: float,
    target_power: float = 0.80,
    alpha: float = 0.05,
    max_n: int = 500_000,
) -> int:
    """Find the minimal integer evaluable sample size per arm meeting target power.

    Uses exponential bracketing followed by integer binary search.

    Args:
        p_control: Control event probability.
        p_treatment: Treatment event probability.
        target_power: Desired statistical power (default: 0.80).
        alpha: Two-sided alpha (default: 0.05).
        max_n: Maximum search cap.

    Returns:
        Minimal integer n per arm such that analytic_power(p_c, p_t, n, alpha) >= target_power.
    """
    if target_power <= alpha:
        return 2

    # Step 1: Exponential bracketing
    low = 2
    high = 4
    while high <= max_n and analytic_power(p_control, p_treatment, high, alpha) < target_power:
        low = high
        high *= 2

    if high > max_n:
        if analytic_power(p_control, p_treatment, max_n, alpha) < target_power:
            raise ValueError(
                f"Required sample size exceeds maximum search limit ({max_n}) for target power {target_power}"
            )
        high = max_n

    # Step 2: Binary search for exact smallest integer n
    ans = high
    while low <= high:
        mid = (low + high) // 2
        pwr = analytic_power(p_control, p_treatment, mid, alpha)
        if pwr >= target_power:
            ans = mid
            high = mid - 1
        else:
            low = mid + 1

    return ans


def calculate_trial_design(
    p_control: float,
    p_treatment: float,
    target_power: float = 0.80,
    alpha: float = 0.05,
    dropout_control: float = 0.0,
    dropout_treatment: float = 0.0,
) -> SampleSizeResult:
    """Calculate complete sample size requirements including attrition inflation.

    Args:
        p_control: Planned control event probability.
        p_treatment: Planned treatment event probability.
        target_power: Target power (e.g. 0.80).
        alpha: Significance level (e.g. 0.05).
        dropout_control: Anticipated control dropout rate in [0, 1).
        dropout_treatment: Anticipated treatment dropout rate in [0, 1).

    Returns:
        SampleSizeResult with evaluable, enrolled counts, and realized nominal power.
    """
    if not (0.0 <= dropout_control < 1.0) or not (0.0 <= dropout_treatment < 1.0):
        raise ValueError("Dropout rates must be in [0, 1).")

    n_eval = solve_evaluable_sample_size(
        p_control=p_control,
        p_treatment=p_treatment,
        target_power=target_power,
        alpha=alpha,
    )

    power = analytic_power(p_control, p_treatment, n_eval, alpha)
    h = cohen_h(p_control, p_treatment)

    # Inflation formula: ceil(n_eval / (1 - d))
    n_enroll_c = math.ceil(n_eval / (1.0 - dropout_control))
    n_enroll_t = math.ceil(n_eval / (1.0 - dropout_treatment))
    n_enrolled_per_arm = max(n_enroll_c, n_enroll_t)

    return SampleSizeResult(
        n_evaluable_per_arm=n_eval,
        total_evaluable=n_eval * 2,
        n_enrolled_per_arm=n_enrolled_per_arm,
        total_enrolled=n_enroll_c + n_enroll_t,
        nominal_power=power,
        effect_size_h=h,
    )
