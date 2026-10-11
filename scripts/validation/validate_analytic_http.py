"""Independent standard-library arcsine/normal oracle against the live local API.

No product imports or statsmodels calls. This validates the analytic model only;
its output is not Monte Carlo, clinical or regulatory validation.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import json
import math
from pathlib import Path
import re
from statistics import NormalDist
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

POWER_TOLERANCE = 1e-10  # Prespecified normal-CDF rounding tolerance.
MAX_ENROLLED = 1_000_000


def power(control, treatment, retained, alpha):
    h = abs(2 * math.asin(math.sqrt(treatment)) - 2 * math.asin(math.sqrt(control)))
    mean = math.sqrt(retained / 2) * h
    critical = NormalDist().inv_cdf(1 - alpha / 2)
    # erfc avoids cancellation in the normal tails; no numerical engine import.
    return .5 * math.erfc((critical - mean) / math.sqrt(2)) + .5 * math.erfc((critical + mean) / math.sqrt(2))


def minimum_n(control, treatment, alpha, target):
    low, high = 1, MAX_ENROLLED
    if power(control, treatment, high, alpha) < target:
        raise ValueError('Oracle sample size exceeds declared per-arm domain')
    while low < high:
        middle = (low + high) // 2
        if power(control, treatment, middle, alpha) >= target:
            high = middle
        else:
            low = middle + 1
    return low


def inflated(n, dropout):
    return int((Decimal(n) / (1 - Decimal(str(dropout)))).to_integral_value(rounding=ROUND_CEILING))


def retained(n, dropout):
    return int(Decimal(n) * (1 - Decimal(str(dropout))))


def post(base, route, payload):
    req = Request(base + route, data=json.dumps(payload, allow_nan=False).encode(),
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        def reject(value):
            raise ValueError(f'Nonfinite JSON: {value}')
        return json.loads(response.read(), parse_constant=reject)


def verify(base, engine_commit):
    parsed = urlsplit(base)
    if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1')
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('Use a local HTTP API origin')
    if not re.fullmatch('[0-9a-f]{40}', engine_commit):
        raise ValueError('Record the full tested backend commit SHA')
    base = base.rstrip('/')
    # Declared before execution: typical risks, RR/ARR, target/alpha and dropout.
    matrix = [(.2, 'relative_risk', .75, .05, .8, 0),
              (.2, 'relative_risk', .75, .05, .8, .1),
              (.1, 'relative_risk', .75, .05, .8, 0),
              (.3, 'relative_risk', .5, .01, .9, .2),
              (.05, 'relative_risk', .75, .05, .8, .3),
              (.2, 'absolute_risk_reduction', .05, .05, .8, 0),
              (.1, 'absolute_risk_reduction', .02, .01, .9, .13),
              (.3, 'absolute_risk_reduction', .05, .05, .7, .1)]
    cases, versions = [], None
    for control, kind, value, alpha, target, dropout in matrix:
        treatment = control * value if kind == 'relative_risk' else control - value
        planned = dict(model_version='binary-v1', control_event_rate=control,
                       effect=dict(kind=kind, value=value), alpha=alpha,
                       target_power=target, allocation_ratio=1,
                       dropout=dict(control=dropout, treatment=dropout))
        design = post(base, '/api/v1/design/calculate', planned)
        expected_n = minimum_n(control, treatment, alpha, target)
        expected_enrolled = inflated(expected_n, dropout)
        assert design['evaluable_n'] == dict(control=expected_n, treatment=expected_n), 'Minimum sample size mismatch'
        assert design['enrolled_n'] == dict(control=expected_enrolled, treatment=expected_enrolled), 'Enrollment inflation mismatch'
        assert power(control, treatment, expected_n, alpha) >= target, 'Oracle missed target'
        assert expected_n == 1 or power(control, treatment, expected_n - 1, alpha) < target, 'Oracle count not minimal'
        assert abs(design['nominal_power_evaluable'] - power(control, treatment, expected_n, alpha)) <= POWER_TOLERANCE, 'Nominal power mismatch'
        scenarios = []
        for stress_control, stress_dropout in ((control, dropout), (control * .5, 0), (control * .75, .25), (control, .58)):
            stress_treatment = stress_control * value if kind == 'relative_risk' else stress_control - value
            request = dict(planned_design=planned, fixed_enrollment=design['enrolled_n'],
                           stress_scenario=dict(control_event_rate=stress_control,
                             dropout=dict(control=stress_dropout, treatment=stress_dropout), effect_override=None),
                           simulation=None)
            actual = post(base, '/api/v1/scenarios/evaluate', request)
            expected_retained = retained(expected_enrolled, stress_dropout)
            expected_power = power(stress_control, stress_treatment, expected_retained, alpha)
            delta = abs(actual['analytic']['conditional_power_approx'] - expected_power)
            assert actual['analytic']['assumed_evaluable_n'] == dict(control=expected_retained, treatment=expected_retained), 'Expected retention mismatch'
            assert actual['metadata']['fixed_enrollment'] == design['enrolled_n'], 'Stress resized enrollment'
            assert actual['monte_carlo'] is None, 'Unexpected simulation'
            assert delta <= POWER_TOLERANCE, f'Power disagreement: {delta}'
            current_versions = actual['metadata']['software_versions']
            assert versions is None or versions == current_versions, 'Environment changed within run'
            versions = current_versions
            scenarios.append(dict(request=request, response=actual, oracle_power=expected_power, absolute_error=delta))
        cases.append(dict(planned_request=planned, design_response=design,
                          oracle_evaluable_n=expected_n, oracle_enrolled_n=expected_enrolled,
                          stress_checks=scenarios))
    return dict(status='passed', scope='analytic_http_only', captured_at=datetime.now(timezone.utc).isoformat(),
                engine_commit=engine_commit, source='real_local_http', software_versions=versions,
                oracle='stdlib math.erfc/arcsine + statistics.NormalDist, independent of product/statsmodels',
                power_tolerance=POWER_TOLERANCE, design_cases=len(cases), stress_cases=sum(len(c['stress_checks']) for c in cases),
                limitations=['Same mathematical approximation, not independent clinical evidence',
                             'Monte Carlo/null calibration and full export evidence remain pending',
                             'Small prespecified matrix, not exhaustive edge-case validation'], cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    parser.add_argument('--engine-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.base_url, args.engine_commit)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'scope', 'design_cases', 'stress_cases', 'power_tolerance')}))
