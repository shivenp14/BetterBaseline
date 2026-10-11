"""Validate an externally captured API→UI-export bundle against frozen schemas.

Requires a real recorded export, never constructs one from an API response.
Fixture-mode checker data belongs only in test_invariants.py.
"""
import argparse
import json
from pathlib import Path

from invariants import canonical_result, check_design, check_evaluation, check_export, check_grid, require

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    def reject(value):
        raise ValueError(f'Nonfinite JSON constant: {value}')
    return json.loads(Path(path).read_text(), parse_constant=reject)


def check_capture(capture, schema):
    from jsonschema import Draft202012Validator
    request = capture['request']
    response = capture['evaluation_response']
    grid = capture['grid_response']
    # $defs are supplied by #63 as read-only artifacts; missing types fail.
    for model, value in (
        ('ScenarioEvaluateRequest', request),
        ('DesignCalculateResponse', canonical_result(capture['design_response'])),
        ('ScenarioEvaluateResponse', canonical_result(response)),
        ('ScenarioGridResponse', grid),
        ('ExportPayload', capture['export']),
    ):
        require(model in schema['$defs'], f'Missing frozen schema {model}')
        # The bundle schema may have a root discriminator/anyOf for a different
        # envelope. Validate the named model directly with the shared defs.
        selected = {'$schema': schema.get('$schema', 'https://json-schema.org/draft/2020-12/schema'),
                    '$defs': schema['$defs'], '$ref': f'#/$defs/{model}'}
        Draft202012Validator(selected).validate(value)
    check_design(request['planned_design'], capture['design_response'])
    check_evaluation(request, response)
    check_grid(request, response, grid, require_grid_node=False)
    check_export(request, response, capture['export'], capture['expected_provenance'])
    require(capture['export']['design_result'] == canonical_result(capture['design_response']), 'export lost design result')
    require(capture['export']['grid_result'] == grid, 'export lost grid result')
    require(capture['source'] == 'real_api_and_ui_export', 'illustrative captures are not live acceptance')
    require(bool(capture['engine_commit']) and bool(capture['captured_at']), 'record commit/date')
    versions = response['metadata']['software_versions']
    require(response['monte_carlo'] is not None, 'this capture requires a seeded simulation run')
    require(all(versions.get(name) for name in ('python', 'numpy', 'scipy', 'statsmodels')), 'missing software provenance')
    require(bool(response['monte_carlo'].get('rng')), 'missing RNG identity')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', help='JSON bundle recorded from real API and independently downloaded UI export')
    parser.add_argument('--schema', default=str(ROOT / 'contracts/api-v1.schema.json'))
    args = parser.parse_args()
    try:
        check_capture(load(args.capture), load(args.schema))
    except (AssertionError, ValueError, KeyError, OSError, ImportError) as error:
        parser.exit(1, f'Integration capture failed: {error}\n')
    print('Captured API/export invariants and schema checks passed; browser/offline evidence is separate.')
