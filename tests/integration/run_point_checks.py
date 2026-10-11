"""Check actual calculate→fixed-enrollment evaluation over local HTTP.

This is partial API integration, not UI export/grid/offline acceptance. Uses the
running app's typed OpenAPI response model as a read-only contract, never an
import of a calculator or a synthetic substitute for an endpoint response.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator
from invariants import check_design, check_evaluation, require

ROOT = Path(__file__).resolve().parents[2]


def reject_nonfinite(value):
    raise ValueError(f'Nonfinite JSON constant: {value}')


def exchange(base, route, payload=None):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    req = Request(base + route, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=5) as response:
        return json.loads(response.read(), parse_constant=reject_nonfinite)


def check_point_api(base):
    parts = urlsplit(base)
    require(parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1')
            and not parts.username and not parts.password and not parts.query
            and not parts.fragment and parts.path in ('', '/'), 'use a local HTTP API origin')
    base = base.rstrip('/')
    deadline = time.monotonic() + 30
    while True:
        try:
            exchange(base, '/healthz')
            break
        except (URLError, OSError):
            if time.monotonic() >= deadline:
                raise RuntimeError('Local API did not become healthy within 30 seconds')
            time.sleep(.25)
    request = json.loads((ROOT / 'demo-data/baseline-collapse-v1/inputs.json').read_text())
    design = exchange(base, '/api/v1/design/calculate', request['planned_design'])
    check_design(request['planned_design'], design)
    require(design['evaluable_n'] == {'control': 903, 'treatment': 903}, 'reference design count')
    require(design['enrolled_n'] == request['fixed_enrollment'], 'calculate/evaluate enrollment handoff')
    request['fixed_enrollment'] = deepcopy(design['enrolled_n'])
    first = exchange(base, '/api/v1/scenarios/evaluate', request)
    check_evaluation(request, first)
    require(abs(first['analytic']['conditional_power_approx'] - .470) <= .005, 'baseline-collapse reference')
    repeat = exchange(base, '/api/v1/scenarios/evaluate', request)
    require(first['analytic'] == repeat['analytic'] and first['monte_carlo'] == repeat['monte_carlo'], 'same-environment seed drift')
    require(first['metadata']['inputs_hash'] == repeat['metadata']['inputs_hash'], 'input identity drift')
    stressed = deepcopy(request)
    stressed['stress_scenario']['dropout'] = {'control': .25, 'treatment': .25}
    second = exchange(base, '/api/v1/scenarios/evaluate', stressed)
    check_evaluation(stressed, second)
    require(second['metadata']['fixed_enrollment'] == design['enrolled_n'], 'stress resized enrolled counts')
    require(first['metadata']['inputs_hash'] != second['metadata']['inputs_hash'], 'changed stress identity not recorded')
    # Validate real responses against the registered endpoint's exact OpenAPI
    # model. Shared export-schema adaptation remains with #67/#76.
    openapi = exchange(base, '/openapi.json')
    components = json.loads(json.dumps(openapi['components']['schemas']).replace('#/components/schemas/', '#/$defs/'))
    ref = openapi['paths']['/api/v1/scenarios/evaluate']['post']['responses']['200']['content']['application/json']['schema']['$ref']
    contract = {'$defs': components, '$ref': ref.replace('#/components/schemas/', '#/$defs/')}
    for response in (first, repeat, second):
        Draft202012Validator(contract).validate(response)
    planned_dropout = deepcopy(request['planned_design'])
    planned_dropout['dropout'] = {'control': .10, 'treatment': .10}
    inflated = exchange(base, '/api/v1/design/calculate', planned_dropout)
    check_design(planned_dropout, inflated)
    require(inflated['enrolled_n'] == {'control': 1004, 'treatment': 1004}, 'dropout inflation reference')
    return {'status': 'passed', 'scope': 'real_calculate_and_evaluate_only',
            'power': first['analytic']['conditional_power_approx'],
            'seed': first['monte_carlo']['seed'],
            'software_versions': first['metadata']['software_versions']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    print(json.dumps(check_point_api(args.base_url), sort_keys=True))
