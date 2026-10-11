"""Check actual calculate→fixed-enrollment evaluation→grid over local HTTP.

This is partial API integration, not UI export/offline acceptance. Uses the
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
from invariants import check_design, check_evaluation, check_grid_handoff, require

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
    def validate(route, value):
        ref = openapi['paths'][route]['post']['responses']['200']['content']['application/json']['schema']['$ref']
        contract = {'$defs': components, '$ref': ref.replace('#/components/schemas/', '#/$defs/')}
        Draft202012Validator(contract).validate(value)

    shared = json.loads((ROOT / 'contracts/api-v1.schema.json').read_text())
    grid_contract = {'$defs': shared['$defs'], '$ref': '#/$defs/ScenarioGridResponse'}

    for response in (first, repeat, second):
        validate('/api/v1/scenarios/evaluate', response)
    validate('/api/v1/design/calculate', design)
    grid_request = {'planned_design': deepcopy(request['planned_design']),
                    'fixed_enrollment': deepcopy(request['fixed_enrollment']),
                    'x_baseline': {'min': .1, 'max': .3, 'steps': 3},
                    'y_dropout': {'min': 0, 'max': .2, 'steps': 2},
                    'selected_scenario': deepcopy(request['stress_scenario'])}
    grid_route = '/api/v1/scenarios/grid'
    evaluation_route = '/api/v1/scenarios/evaluate'
    grids = []
    for dropout in (0, .13):
        selected_request = deepcopy(request)
        selected_request['simulation'] = None
        selected_request['stress_scenario']['dropout'] = {'control': dropout, 'treatment': dropout}
        selected_response = exchange(base, evaluation_route, selected_request)
        check_evaluation(selected_request, selected_response)
        validate(evaluation_route, selected_response)
        grid_request['selected_scenario'] = deepcopy(selected_request['stress_scenario'])
        grid = exchange(base, grid_route, grid_request)
        validate(grid_route, grid)
        Draft202012Validator(grid_contract).validate(grid)
        curve_responses = []
        for baseline in grid['x_baseline']:
            point_request = deepcopy(selected_request)
            point_request['stress_scenario']['control_event_rate'] = baseline
            point = exchange(base, evaluation_route, point_request)
            check_evaluation(point_request, point)
            validate(evaluation_route, point)
            curve_responses.append(point)
        check_grid_handoff(selected_request, selected_response, grid_request, grid, curve_responses)
        grids.append(grid)
    require(grids[0]['inputs_hash'] != grids[1]['inputs_hash'], 'grid identity did not change with selected dropout')
    require(grids[0]['planned_point'] == grids[1]['planned_point'], 'stress mutated original planned comparison')
    # Check every nonsquare matrix cell against a separate HTTP point evaluation.
    for row, dropout in zip(grids[0]['power'], grids[0]['y_dropout']):
        for cell, baseline in zip(row, grids[0]['x_baseline']):
            point_request = deepcopy(request)
            point_request['simulation'] = None
            point_request['stress_scenario'].update(control_event_rate=baseline,
                dropout={'control': dropout, 'treatment': dropout})
            point = exchange(base, evaluation_route, point_request)
            require(abs(cell - point['analytic']['conditional_power_approx']) < 1e-10,
                    'grid row/column disagrees with independent point evaluation')
    # ARR .15 is invalid at .10 but valid at .20/.30. Never substitute zero.
    arr_request = deepcopy(grid_request)
    arr_request['selected_scenario']['control_event_rate'] = .2
    arr_request['selected_scenario']['effect_override'] = {'kind': 'absolute_risk_reduction', 'value': .15}
    arr_grid = exchange(base, grid_route, arr_request)
    validate(grid_route, arr_grid)
    Draft202012Validator(grid_contract).validate(arr_grid)
    require(arr_grid['invalid_mask'] == [[True, False, False], [True, False, False]], 'ARR invalid-mask orientation')
    require(all(row[0] is None for row in arr_grid['power'])
            and arr_grid['power_curve'][0]['power'] is None
            and arr_grid['power_curve'][0]['is_valid'] is False, 'ARR invalid cells/curve must be null')
    require(arr_grid['invalid_cell_count'] == 2, 'ARR invalid-cell count')
    require(arr_grid['planned_point'] == grids[0]['planned_point'], 'stress effect mutated original plan')
    for row, dropout in zip(arr_grid['power'], arr_grid['y_dropout']):
        for baseline, cell in zip(arr_grid['x_baseline'][1:], row[1:]):
            point_request = deepcopy(request)
            point_request['simulation'] = None
            point_request['stress_scenario'] = {'control_event_rate': baseline,
                'dropout': {'control': dropout, 'treatment': dropout},
                'effect_override': {'kind': 'absolute_risk_reduction', 'value': .15}}
            point = exchange(base, evaluation_route, point_request)
            require(abs(cell - point['analytic']['conditional_power_approx']) < 1e-10, 'ARR grid/point effect mismatch')
    planned_dropout = deepcopy(request['planned_design'])
    planned_dropout['dropout'] = {'control': .10, 'treatment': .10}
    inflated = exchange(base, '/api/v1/design/calculate', planned_dropout)
    check_design(planned_dropout, inflated)
    require(inflated['enrolled_n'] == {'control': 1004, 'treatment': 1004}, 'dropout inflation reference')
    validate('/api/v1/design/calculate', inflated)
    return {'status': 'passed', 'scope': 'real_calculate_evaluate_and_grid',
            'grid_shape': [2, 3], 'off_grid_dropout': .13, 'arr_invalid_cells': 2,
            'power': first['analytic']['conditional_power_approx'],
            'seed': first['monte_carlo']['seed'],
            'software_versions': first['metadata']['software_versions']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    print(json.dumps(check_point_api(args.base_url), sort_keys=True))
