"""Vectorized Monte Carlo simulation engine for two-arm clinical trials.

Simulates thousands of clinical trial replications in parallel using NumPy:
1. Arm-specific dropout / retention via Binomial draws.
2. Binary event outcomes via Binomial draws.
3. Pooled two-proportion z-test statistics.
4. Two-sided empirical power and favorable-direction empirical power.
5. Monte Carlo Standard Error (MCSE) calculation.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class SimulationParams:
    n_enrolled_control: int
    n_enrolled_treatment: int
    p_control: float
    p_treatment: float
    dropout_control: float = 0.0
    dropout_treatment: float = 0.0
    alpha: float = 0.05
    replications: int = 10_000
    seed: Optional[int] = 42


@dataclass(frozen=True)
class SimulationResult:
    replications: int
    alpha: float
    power_two_sided: float
    power_favorable: float
    mcse_two_sided: float
    mcse_favorable: float
    mean_retained_control: float
    mean_retained_treatment: float
    mean_events_control: float
    mean_events_treatment: float
    invalid_trials_count: int
    invalid_trials_rate: float


def simulate_binary_trials(params: SimulationParams) -> SimulationResult:
    """Run vectorized Monte Carlo clinical trial simulation.

    Args:
        params: Simulation parameters including arm sizes, probabilities, and reps.

    Returns:
        SimulationResult containing empirical power, MCSE, and trial diagnostics.
    """
    if params.n_enrolled_control < 2 or params.n_enrolled_treatment < 2:
        raise ValueError("Enrolled sample size per arm must be at least 2.")
    if not (0.0 < params.p_control < 1.0) or not (0.0 < params.p_treatment < 1.0):
        raise ValueError("Event probabilities must be strictly in (0, 1).")
    if not (0.0 <= params.dropout_control < 1.0) or not (0.0 <= params.dropout_treatment < 1.0):
        raise ValueError("Dropout probabilities must be in [0, 1).")
    if params.replications < 100:
        raise ValueError("Replications must be at least 100.")

    rng = np.random.default_rng(params.seed)

    # 1. Simulate retention / attrition per arm across all replications
    ret_c = rng.binomial(
        n=params.n_enrolled_control,
        p=1.0 - params.dropout_control,
        size=params.replications,
    )
    ret_t = rng.binomial(
        n=params.n_enrolled_treatment,
        p=1.0 - params.dropout_treatment,
        size=params.replications,
    )

    # 2. Simulate binary event outcomes on retained subjects
    events_c = rng.binomial(n=ret_c, p=params.p_control)
    events_t = rng.binomial(n=ret_t, p=params.p_treatment)

    # 3. Guard against degenerate samples (0 retained, or pooled rate 0 or 1)
    valid_mask = (ret_c > 0) & (ret_t > 0)
    total_retained = ret_c + ret_t
    total_events = events_c + events_t

    # Degenerate: no variance (all events or zero events across both arms)
    valid_mask &= (total_events > 0) & (total_events < total_retained)

    invalid_count = int(np.sum(~valid_mask))
    invalid_rate = float(invalid_count / params.replications)

    if invalid_count == params.replications:
        # 100% degenerate/invalid
        return SimulationResult(
            replications=params.replications,
            alpha=params.alpha,
            power_two_sided=0.0,
            power_favorable=0.0,
            mcse_two_sided=0.0,
            mcse_favorable=0.0,
            mean_retained_control=float(np.mean(ret_c)),
            mean_retained_treatment=float(np.mean(ret_t)),
            mean_events_control=float(np.mean(events_c)),
            mean_events_treatment=float(np.mean(events_t)),
            invalid_trials_count=invalid_count,
            invalid_trials_rate=invalid_rate,
        )

    # Calculate statistics only for valid trials
    valid_ret_c = ret_c[valid_mask]
    valid_ret_t = ret_t[valid_mask]
    valid_events_c = events_c[valid_mask]
    valid_events_t = events_t[valid_mask]

    p_hat_c = valid_events_c / valid_ret_c
    p_hat_t = valid_events_t / valid_ret_t
    p_pooled = (valid_events_c + valid_events_t) / (valid_ret_c + valid_ret_t)

    # Standard error under null
    se_pooled = np.sqrt(p_pooled * (1.0 - p_pooled) * (1.0 / valid_ret_c + 1.0 / valid_ret_t))
    z = (p_hat_t - p_hat_c) / se_pooled

    # Two-sided p-value: 2 * norm.sf(|z|)
    p_values = 2.0 * norm.sf(np.abs(z))

    # Two-sided rejection
    rej_two_sided = p_values < params.alpha

    # Favorable direction: lower event rate in treatment arm (p_hat_t < p_hat_c)
    rej_favorable = rej_two_sided & (p_hat_t < p_hat_c)

    # In terms of total replications:
    # invalid replications are treated as non-rejections
    power_two_sided = float(np.sum(rej_two_sided) / params.replications)
    power_favorable = float(np.sum(rej_favorable) / params.replications)

    mcse_two_sided = float(np.sqrt(power_two_sided * (1.0 - power_two_sided) / params.replications))
    mcse_favorable = float(np.sqrt(power_favorable * (1.0 - power_favorable) / params.replications))

    return SimulationResult(
        replications=params.replications,
        alpha=params.alpha,
        power_two_sided=power_two_sided,
        power_favorable=power_favorable,
        mcse_two_sided=mcse_two_sided,
        mcse_favorable=mcse_favorable,
        mean_retained_control=float(np.mean(ret_c)),
        mean_retained_treatment=float(np.mean(ret_t)),
        mean_events_control=float(np.mean(events_c)),
        mean_events_treatment=float(np.mean(events_t)),
        invalid_trials_count=invalid_count,
        invalid_trials_rate=invalid_rate,
    )
