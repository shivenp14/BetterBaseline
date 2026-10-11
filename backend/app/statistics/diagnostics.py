"""Transport-independent diagnostics for conditional binary-trial power.

Import these helpers directly from ``app.statistics.diagnostics``. They return
JSON-safe dictionaries with ``valid`` and ordered ``diagnostics`` entries. An
error means no supported calculation should be displayed (use null/mask in a
grid); warnings leave otherwise-valid cells calculable. No helper calculates,
clips, or substitutes a power estimate. API adapters own HTTP serialization.

Expected events OR non-events strictly below 5 in either arm trigger an
approximation warning. Analytic checks use the supplied floored evaluable counts;
simulation checks use enrollment * (1-dropout), never floored counts or a promise
of actual retention. Rates <= .01 or >= .99 additionally trigger a near-boundary
warning: this is a descriptive heuristic, not a validity cutoff. Low counts and
near-boundary rates do not by themselves reject a scenario.

Cohen's-h normal power and simulated pooled-z rejection fractions are distinct
approximations. Simulation does not cure the pooled-z test's small-sample limits.
Undefined simulated tests remain nonrejections over ALL replicates; even an
all-invalid run is disclosed rather than recast as a valid zero-power result.
Every estimate is conditional on stated endpoint, effect, independent dropout,
and analysis assumptions, not efficacy, clinical evidence, or a recommendation.
"""

from .analytic import COHEN_H_NORMAL_METHOD
from .errors import StatisticalInputError
from .inputs import Dropout, FixedEnrollment
from .validation import finite_number, probability

EXPECTED_COUNT_THRESHOLD = 5
NEAR_BOUNDARY_THRESHOLD = .01
POOLED_Z_METHOD = "pooled_two_proportion_z_v1"


def _entry(code, severity, field, method, message, **details):
    return dict(code=code, severity=severity, field=field, method=method,
                message=message, **details)


def _rejected(error, method):
    # Never echo the invalid input (it may be NaN, infinity, or non-JSON data).
    return {"valid": False, "diagnostics": [
        _entry(error.code, "error", error.field, method, str(error)),
    ]}


def _base(method):
    return [_entry(
        "CONDITIONAL_POWER_ONLY", "info", "interpretation", method,
        "Estimate conditional on stated assumptions; not efficacy, clinical "
        "evidence, or a clinical recommendation.",
    )]


def _arm_warnings(method, arm, rate, count, count_basis):
    entries = []
    field = f"p_{arm}" if method == COHEN_H_NORMAL_METHOD else f"{arm}_event_rate"
    for outcome, expected in (("events", count * rate),
                              ("non_events", count * (1 - rate))):
        if expected < EXPECTED_COUNT_THRESHOLD:
            entries.append(_entry(
                "LOW_EXPECTED_COUNT", "warning", field, method,
                f"{arm.capitalize()} expected {outcome.replace('_', '-')} below 5; "
                f"{'Cohen’s-h normal' if method == COHEN_H_NORMAL_METHOD else 'pooled-z test'} "
                "approximation may be unreliable.",
                arm=arm, outcome=outcome, expected_count=expected,
                threshold=EXPECTED_COUNT_THRESHOLD, count_basis=count_basis,
            ))
    if rate <= NEAR_BOUNDARY_THRESHOLD or rate >= 1 - NEAR_BOUNDARY_THRESHOLD:
        entries.append(_entry(
            "NEAR_BOUNDARY_PROBABILITY", "warning", field, method,
            "Event probability near zero or one; the normal approximation may "
            "be unreliable. This heuristic does not reject the scenario.",
            arm=arm, threshold=NEAR_BOUNDARY_THRESHOLD,
        ))
    return entries


def analytic_diagnostics(p_control, p_treatment, n_control_evaluable,
                         n_treatment_evaluable, alpha=.05, *,
                         method=COHEN_H_NORMAL_METHOD):
    """Check the canonical analytic domain without computing a power value.

    Invalid inputs use existing StatisticalInputError codes/fields. Zero
    evaluable counts get ZERO_EVALUABLE_COUNT rather than fabricated zero power.
    Equal event probabilities are supported for null calibration.
    """
    try:
        if method != COHEN_H_NORMAL_METHOD:
            raise StatisticalInputError("Unsupported analytic power method",
                                        field="method", code="UNSUPPORTED_MODEL")
        control = probability(p_control, field="p_control")
        treatment = probability(p_treatment, field="p_treatment")
        probability(alpha, field="alpha")
        for arm, count in (("control", n_control_evaluable),
                           ("treatment", n_treatment_evaluable)):
            if isinstance(count, int) and not isinstance(count, bool) and count == 0:
                raise StatisticalInputError(
                    "Zero evaluable participants; analytic power is undefined",
                    field=f"n_{arm}_evaluable", code="ZERO_EVALUABLE_COUNT",
                )
        enrollment = FixedEnrollment(n_control_evaluable, n_treatment_evaluable)
        # Guard count arithmetic before emitting any nonfinite JSON values.
        counts = [finite_number(getattr(enrollment, arm), field=f"n_{arm}_evaluable")
                  for arm in ("control", "treatment")]
    except StatisticalInputError as error:
        return _rejected(error, COHEN_H_NORMAL_METHOD)
    entries = _base(method)
    for arm, rate, count in zip(("control", "treatment"), (control, treatment), counts):
        entries.extend(_arm_warnings(method, arm, rate, count, "evaluable_count"))
    return {"valid": True, "diagnostics": entries}


def simulation_diagnostics(n_c, n_t, p_c, p_t, d_c, d_t, alpha=.05, *,
                           method=POOLED_Z_METHOD, invalid_test_fraction=None,
                           replicates=None):
    """Check simulation assumptions and optionally disclose observed invalid tests.

    Pass invalid_test_fraction and replicates together from simulate_binary's
    result. Neither is inferred from the input regime. The validity flag refers
    to supported inputs, not a claim that every simulated test was defined.
    """
    # Import only on use so analytic diagnostics need no NumPy/SciPy runtime.
    from .simulation import MAX_ENROLLED_PER_ARM, MAX_REPLICATES, _bounded_integer

    try:
        if method != POOLED_Z_METHOD:
            raise StatisticalInputError("Unsupported simulation method", field="method",
                                        code="UNSUPPORTED_MODEL")
        enrollment = FixedEnrollment(n_c, n_t)
        dropout = Dropout(d_c, d_t)
        control = probability(p_c, field="control_event_rate")
        treatment = probability(p_t, field="treatment_event_rate")
        probability(alpha, field="alpha")
        for arm in ("control", "treatment"):
            _bounded_integer(getattr(enrollment, arm), field=f"enrolled_n.{arm}",
                             minimum=1, maximum=MAX_ENROLLED_PER_ARM)
        if (invalid_test_fraction is None) != (replicates is None):
            raise StatisticalInputError(
                "Invalid-test frequency and replicate count must be supplied together",
                field="invalid_test_fraction",
            )
        fraction = None
        if invalid_test_fraction is not None:
            fraction = finite_number(invalid_test_fraction, field="invalid_test_fraction")
            if not 0 <= fraction <= 1:
                raise StatisticalInputError("Expected a frequency in [0, 1]",
                                            field="invalid_test_fraction")
            _bounded_integer(replicates, field="replicates", minimum=1,
                             maximum=MAX_REPLICATES)
    except StatisticalInputError as error:
        return _rejected(error, POOLED_Z_METHOD)
    entries = _base(method)
    entries.append(_entry(
        "DISTINCT_METHOD_APPROXIMATIONS", "info", "method", method,
        "Pooled-z simulation and Cohen's-h analytic power use distinct "
        "approximations; Monte Carlo does not remove pooled-z small-sample limits.",
    ))
    for arm, rate in (("control", control), ("treatment", treatment)):
        count = getattr(enrollment, arm) * (1 - getattr(dropout, arm))
        entries.extend(_arm_warnings(method, arm, rate, count, "expected_random_retention"))
    if fraction is not None and fraction > 0:
        entries.append(_entry(
            "ALL_SIMULATED_TESTS_INVALID" if fraction == 1 else "INVALID_SIMULATED_TESTS",
            "warning", "invalid_test_fraction", method,
            "Undefined pooled-z tests (empty arms, zero variance, or nonfinite "
            "statistics) count as nonrejections over all replicates; rejection "
            "fractions must be read with this frequency.",
            invalid_test_fraction=fraction, replicates=replicates,
            invalid_test_policy="nonrejection_over_all_replicates",
        ))
    return {"valid": True, "diagnostics": entries}
