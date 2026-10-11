"""Compare independently captured API results with statsmodels' normal-power API.

Imports no product modules. This supplements the standard-library implementation;
all implement the same Cohen-h approximation, not separate clinical models.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import statsmodels
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

TOLERANCE = 1e-10  # Fixed before any comparison.


def verify(capture):
    calculator = NormalIndPower()
    rows = []

    def power(control, effect, n, alpha):
        treatment = control * effect['value'] if effect['kind'] == 'relative_risk' else control - effect['value']
        h = abs(proportion_effectsize(control, treatment))
        return float(calculator.power(h, nobs1=n, alpha=alpha, ratio=1, alternative='two-sided'))

    for case in capture['cases']:
        planned, response = case['planned_request'], case['design_response']
        n = response['evaluable_n']['control']
        expected = power(planned['control_event_rate'], planned['effect'], n, planned['alpha'])
        assert expected >= planned['target_power']
        assert n == 1 or power(planned['control_event_rate'], planned['effect'], n - 1, planned['alpha']) < planned['target_power']
        error = abs(expected - response['nominal_power_evaluable'])
        assert error <= TOLERANCE, error
        rows.append({'scope': 'minimal_design', 'n': n, 'package_power': expected, 'absolute_error': error})
        for scenario in case['stress_checks']:
            stress, actual = scenario['request']['stress_scenario'], scenario['response']['analytic']
            n = actual['assumed_evaluable_n']['control']
            expected = power(stress['control_event_rate'], stress['effect_override'] or planned['effect'], n, planned['alpha'])
            error = abs(expected - actual['conditional_power_approx'])
            assert error <= TOLERANCE, error
            rows.append({'scope': 'fixed_enrollment_stress', 'n': n, 'package_power': expected, 'absolute_error': error})
    return {'status': 'pass', 'captured_at': datetime.now(timezone.utc).isoformat(),
            'engine_commit': capture['engine_commit'], 'statsmodels_version': statsmodels.__version__,
            'package_api': 'NormalIndPower.power + proportion_effectsize; no product imports',
            'power_tolerance': TOLERANCE, 'comparisons': len(rows),
            'maximum_absolute_error': max(row['absolute_error'] for row in rows), 'results': rows,
            'limitation': 'Rechecks independently captured HTTP results using an established implementation of the same approximation; not clinical validation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(json.loads(args.input.read_text()))
    try:
        with args.output.open('x') as report:
            report.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    except FileExistsError:
        parser.error(f'Output report already exists: {args.output}; choose a new path to preserve existing evidence')
    print(json.dumps({key: value for key, value in result.items() if key != 'results'}))
