"""Seeded binary trials at fixed enrollment, with independent arm retention.

Uses A1's scalar/P0 validation helpers. This primitive accepts equal true rates
for null calibration, unlike design-search effect inputs. Reproducibility is
within the recorded software environment and draw order, not across RNG versions.
"""

import math
import platform

import numpy as np
import scipy
from scipy.stats import norm

from .errors import StatisticalInputError
from .inputs import Dropout, FixedEnrollment
from .validation import probability


METHOD = "pooled_two_proportion_z_v1"
MAX_REPLICATES = 100_000
MAX_ENROLLED_PER_ARM = 1_000_000
MAX_SEED = 2**32 - 1


def _bounded_integer(value: int, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StatisticalInputError("Expected an integer", field=field)
    if not minimum <= value <= maximum:
        raise StatisticalInputError(
            f"Expected an integer in {minimum}..{maximum}", field=field,
        )
    return value


def simulate_binary(
    n_c: int, n_t: int,
    p_c: float, p_t: float,
    d_c: float, d_t: float,
    alpha: float = .05,
    reps: int = 10_000,
    seed: int = 42,
) -> dict:
    """Return pooled-z rejection estimates and count aggregates, never raw trials.

    Enrollment is equal and positive (at most 1,000,000 per arm), and dropout is
    symmetric in [0,1). Arm retention and endpoint draws remain independent.
    Event rates and alpha lie in (0,1); rates may be equal or unfavorable for
    primitive-level calibration. Reps must be an integer in 1..100,000 and seed
    an integer in 0..2**32-1. Booleans/coercible strings are rejected.

    Fixed draw order: retained control, retained treatment, control events,
    treatment events. Use local explicit PCG64 state, never the global RNG.
    Undefined tests (empty arm/zero variance/nonfinite statistic) contribute
    nonrejections to both estimates; every denominator includes all replicates.
    Positive z means more treatment events, so favorable significance has z<0.
    """
    enrollment = FixedEnrollment(n_c, n_t)
    dropout = Dropout(d_c, d_t)
    control_rate = probability(p_c, field="control_event_rate")
    treatment_rate = probability(p_t, field="treatment_event_rate")
    alpha = probability(alpha, field="alpha")
    reps = _bounded_integer(reps, field="replicates", minimum=1, maximum=MAX_REPLICATES)
    seed = _bounded_integer(seed, field="seed", minimum=0, maximum=MAX_SEED)
    for arm in ("control", "treatment"):
        _bounded_integer(getattr(enrollment, arm), field=f"enrolled_n.{arm}",
                         minimum=1, maximum=MAX_ENROLLED_PER_ARM)

    rng = np.random.Generator(np.random.PCG64(seed))
    retained_control = rng.binomial(enrollment.control, 1 - dropout.control, size=reps)
    retained_treatment = rng.binomial(enrollment.treatment, 1 - dropout.treatment, size=reps)
    events_control = rng.binomial(retained_control, control_rate)
    events_treatment = rng.binomial(retained_treatment, treatment_rate)

    rate_control = np.divide(events_control, retained_control,
                             out=np.zeros(reps), where=retained_control > 0)
    rate_treatment = np.divide(events_treatment, retained_treatment,
                               out=np.zeros(reps), where=retained_treatment > 0)
    total_retained = retained_control + retained_treatment
    pooled = np.divide(events_control + events_treatment, total_retained,
                       out=np.zeros(reps), where=total_retained > 0)
    inverse_control = np.divide(1.0, retained_control,
                                out=np.zeros(reps), where=retained_control > 0)
    inverse_treatment = np.divide(1.0, retained_treatment,
                                  out=np.zeros(reps), where=retained_treatment > 0)
    standard_error = np.sqrt(pooled * (1 - pooled) * (inverse_control + inverse_treatment))
    valid = ((retained_control > 0) & (retained_treatment > 0)
             & (standard_error > 0) & np.isfinite(standard_error))
    z = np.divide(rate_treatment - rate_control, standard_error,
                  out=np.zeros(reps), where=valid)
    valid &= np.isfinite(z)
    # Compare in log space: alpha/2 may underflow for very small valid alpha.
    significant = valid & (norm.logsf(np.abs(z)) < math.log(alpha) - math.log(2))
    favorable = significant & (z < 0)

    two_sided_fraction = float(significant.mean())
    favorable_fraction = float(favorable.mean())
    invalid_fraction = float((~valid).mean())
    warnings = [
        "Synthetic outcomes conditional on assumptions; not clinical evidence.",
        "Pooled-z simulation and Cohen's-h analytic power use distinct approximations.",
    ]
    if invalid_fraction > 0:
        warnings.append("Undefined tests count as nonrejections over all replicates.")
    for arm, rate, drop in (("control", control_rate, dropout.control),
                            ("treatment", treatment_rate, dropout.treatment)):
        expected_retained = getattr(enrollment, arm) * (1 - drop)
        if min(expected_retained * rate, expected_retained * (1 - rate)) < 5:
            warnings.append(f"{arm.capitalize()} expected events or nonevents below 5; pooled-z approximation may be unreliable.")

    return {
        "method": METHOD,
        "significant_two_sided_fraction": two_sided_fraction,
        "significant_favorable_fraction": favorable_fraction,
        "mcse_two_sided": math.sqrt(two_sided_fraction * (1 - two_sided_fraction) / reps),
        "mcse_favorable": math.sqrt(favorable_fraction * (1 - favorable_fraction) / reps),
        "invalid_test_fraction": invalid_fraction,
        "invalid_test_policy": "nonrejection_over_all_replicates",
        "mean_retained_control": float(retained_control.mean()),
        "mean_retained_treatment": float(retained_treatment.mean()),
        "mean_control_events": float(events_control.mean()),
        "mean_treatment_events": float(events_treatment.mean()),
        "replicates": reps,
        "seed": seed,
        "rng": "numpy.random.PCG64",
        "software_versions": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "warnings": warnings,
    }
