"""#66 real registered API acceptance; run PYTHONPATH=backend python -m pytest backend/tests/test_api_grid.py."""
from dataclasses import replace
from datetime import datetime
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import grid
from app.schemas import ExportPayload
from app.statistics.analytic import analytic_power
from app.statistics.inputs import expected_retained_count


def payload():
    return {'planned_design': {'model_version': 'binary-v1', 'control_event_rate': .2,
        'effect': {'kind': 'relative_risk', 'value': .75}, 'alpha': .05,
        'target_power': .8, 'allocation_ratio': 1, 'dropout': {'control': .1, 'treatment': .1}},
        'fixed_enrollment': {'control': 1004, 'treatment': 1004},
        'x_baseline': {'min': .1, 'max': .3, 'steps': 3},
        'y_dropout': {'min': 0, 'max': .2, 'steps': 2},
        'selected_scenario': {'control_event_rate': .15, 'dropout': {'control': .13, 'treatment': .13}}}


class GridApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def post(self, body):
        return self.client.post('/api/v1/scenarios/grid', json=body)

    def success(self, body):
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_real_asymmetric_grid_exact_curve_and_off_grid_points(self):
        body = payload()
        result = self.success(body)
        self.assertEqual(result['fixed_enrollment'], body['fixed_enrollment'])
        self.assertEqual(result['y_dropout'], [0, .2])
        self.assertEqual(len(result['power']), 2)
        self.assertEqual([len(row) for row in result['power']], [3, 3])
        for row, dropout in zip(result['power'], result['y_dropout']):
            n = expected_retained_count(1004, dropout)
            for power, baseline in zip(row, result['x_baseline']):
                self.assertAlmostEqual(power, analytic_power(baseline, baseline*.75, n, n, .05).power)
        n = expected_retained_count(1004, .13)
        for point, baseline in zip(result['power_curve'], result['x_baseline']):
            self.assertAlmostEqual(point['power'], analytic_power(baseline, baseline*.75, n, n, .05).power)
        planned, selected = result['planned_point'], result['selected_point']
        self.assertEqual(planned['expected_evaluable_n'], {'control': 903, 'treatment': 903})
        self.assertEqual(selected['dropout'], .13)
        self.assertEqual(selected['p_control'], .15)
        self.assertAlmostEqual(planned['power'], analytic_power(.2, .15, 903, 903, .05).power)
        self.assertAlmostEqual(result['analytic_delta'], selected['power']-planned['power'])
        self.assertEqual(result['invalid_cell_count'], 0)
        self.assertAlmostEqual(result['worst_case_power'], min(map(min, result['power'])))
        self.assertEqual(result['grid_label'], 'expected_count_approximation')
        self.assertEqual(result['method'], 'cohen_h_normal_v1')
        self.assertTrue(datetime.fromisoformat(result['computed_at']).tzinfo)
        self.assertEqual(set(result['software_versions']), {'python', 'numpy', 'scipy', 'statsmodels'})
        diagnostic = next(item for item in result['diagnostics']
                          if item['code'] == 'CONDITIONAL_POWER_ONLY')
        self.assertEqual(diagnostic['field'], 'interpretation')
        self.assertEqual(diagnostic['method'], 'cohen_h_normal')
        self.assertEqual(diagnostic['severity'], 'info')

    def test_default_selected_point_and_curve_use_zero_dropout(self):
        body = payload()
        del body['selected_scenario']
        result = self.success(body)
        self.assertEqual(result['selected_point']['dropout'], 0)
        self.assertEqual([p['power'] for p in result['power_curve']], result['power'][0])

    def test_invalid_arr_cells_are_null_not_zero(self):
        body = payload()
        body['effect_override'] = {'kind': 'absolute_risk_reduction', 'value': .15}
        result = self.success(body)
        self.assertEqual(result['invalid_mask'], [[True, False, False], [True, False, False]])
        self.assertEqual(result['invalid_cell_count'], 2)
        self.assertIsNone(result['power'][0][0])
        self.assertIsNone(result['power_curve'][0]['power'])
        self.assertIsNone(result['selected_point']['power'])
        self.assertEqual(result['selected_point']['invalid_reason'], 'INVALID_EFFECT_AT_BASELINE')
        self.assertIsNone(result['analytic_delta'])
        self.assertFalse(result['selected_point']['is_safe'])
        self.assertIsNone(result['below_target'][0][0])
        selected_diagnostic = next(item for item in result['diagnostics']
                                   if item['severity'] == 'error')
        self.assertEqual(selected_diagnostic['code'], 'INVALID_MODEL_INPUT')
        self.assertEqual(selected_diagnostic['field'], 'p_treatment')
        self.assertEqual(selected_diagnostic['method'], 'cohen_h_normal')
        self.assertIsNone(selected_diagnostic['expected_count'])
        self.assertIn('Selected point is unavailable: INVALID_EFFECT_AT_BASELINE.', result['warnings'])

    def test_all_invalid_low_retention_points_keep_structured_diagnostics(self):
        body = payload()
        body['fixed_enrollment'] = {'control': 1, 'treatment': 1}
        body['x_baseline'] = {'min': .1, 'max': .3, 'steps': 3}
        body['y_dropout'] = {'min': 0, 'max': .2, 'steps': 2}
        del body['selected_scenario']
        result = self.success(body)
        self.assertEqual(result['invalid_cell_count'], 6)
        self.assertIsNone(result['planned_point']['power'])
        self.assertEqual(result['planned_point']['invalid_reason'], 'INSUFFICIENT_EXPECTED_RETAINED')
        self.assertIsNone(result['selected_point']['power'])
        self.assertEqual(result['selected_point']['invalid_reason'], 'INSUFFICIENT_EXPECTED_RETAINED')
        low_count = next(item for item in result['diagnostics'] if item['code'] == 'LOW_EXPECTED_COUNT')
        self.assertIn(low_count['field'], {'p_control', 'p_treatment'})
        self.assertEqual(low_count['method'], 'cohen_h_normal')
        self.assertEqual(low_count['severity'], 'warning')
        self.assertEqual(low_count['count_basis'], 'evaluable_count')
        self.assertNotIn('power', low_count)
        self.assertIn('All grid cells are invalid; worst-case power is unavailable and the frontier is empty.',
                      result['warnings'])
        self.assertIn('Selected point is unavailable: INSUFFICIENT_EXPECTED_RETAINED.', result['warnings'])

    def test_effect_override_preserves_original_planned_power(self):
        body = payload()
        original = self.success(body)
        body['selected_scenario']['effect_override'] = {'kind': 'relative_risk', 'value': .5}
        result = self.success(body)
        self.assertEqual(result['planned_point'], original['planned_point'])
        self.assertGreater(result['selected_point']['power'], original['selected_point']['power'])
        self.assertAlmostEqual(result['analytic_delta'], result['selected_point']['power']-original['planned_point']['power'])

    def test_all_invalid_retention_and_decimal_floor_regression(self):
        body = payload()
        body['fixed_enrollment'] = {'control': 1000, 'treatment': 1000}
        body['selected_scenario']['dropout'] = {'control': .8, 'treatment': .8}
        result = self.success(body)
        self.assertEqual(result['selected_point']['expected_evaluable_n']['control'], 200)
        body['y_dropout'] = {'min': .999, 'max': .9999, 'steps': 2}
        result = self.success(body)
        self.assertEqual(result['invalid_cell_count'], 6)
        self.assertEqual(result['invalid_mask'], [[True]*3]*2)
        self.assertIsNone(result['worst_case_power'])
        self.assertIsNotNone(result['analytic_delta'])
        self.assertAlmostEqual(result['analytic_delta'], result['selected_point']['power'] - result['planned_point']['power'])
        self.assertEqual(result['contour_segments'], [])
        self.assertTrue(any('All grid cells' in w for w in result['warnings']))

    def test_target_contours_match_engine_paths_without_flattening(self):
        body = payload()
        body['x_baseline'] = {'min': .05, 'max': .5, 'steps': 11}
        body['y_dropout'] = {'min': 0, 'max': .5, 'steps': 7}
        real_engine = grid.stress_grid
        captured = []
        def capture(*args, **kwargs):
            value = real_engine(*args, **kwargs)
            captured.append(value)
            return value
        with patch.object(grid, 'stress_grid', side_effect=capture):
            result = self.success(body)
        expected = [{'start': {'p_control': a.baseline, 'dropout': a.dropout},
                     'end': {'p_control': b.baseline, 'dropout': b.dropout}}
                    for path in captured[0].frontier_points for a, b in zip(path.points, path.points[1:])]
        self.assertTrue(expected)
        self.assertEqual(result['contour_segments'], expected)
        coordinates = {(p['p_control'], p['dropout']) for p in result['frontier_points']}
        self.assertEqual(coordinates, {(p['p_control'], p['dropout']) for edge in expected for p in edge.values()})
        self.assertTrue(all(p['power'] == result['target_power'] for p in result['frontier_points']))
        body['planned_design']['target_power'] = .65
        changed = self.success(body)
        self.assertEqual(changed['target_power'], .65)
        self.assertNotEqual(changed['contour_segments'], expected)
        for row, powers in zip(changed['below_target'], changed['power']):
            self.assertEqual(row, [p < .65 if p is not None else None for p in powers])

    def test_malformed_engine_outputs_return_structured_500(self):
        body = payload()
        engine = grid.stress_grid
        mutations = [lambda r: replace(r, power=r.power[:-1]),
                     lambda r: replace(r, power=((.3,),)+r.power[1:]),
                     lambda r: replace(r, invalid_mask=((True,)*3,)+r.invalid_mask[1:]),
                     lambda r: replace(r, below_target=((True,),)+r.below_target[1:]),
                     lambda r: replace(r, power_curve=r.power_curve[:-1]),
                     lambda r: replace(r, x_baseline=(.1,.2,.4))]
        for mutate in mutations:
            with self.subTest(mutate=mutate), patch.object(grid, 'stress_grid', side_effect=lambda *a, **kw: mutate(engine(*a, **kw))):
                response = self.post(body)
                self.assertEqual(response.status_code, 500, response.text)
                self.assertEqual(response.json()['error']['code'], 'INTERNAL_SERVER_ERROR')

    def test_invalid_requests_do_not_call_engine(self):
        cases = []
        for axis, key, value in [('x_baseline','steps',82), ('y_dropout','steps',62),
                                 ('x_baseline','steps',3.0), ('x_baseline','steps',True),
                                 ('x_baseline','min',.3), ('x_baseline','min',0)]:
            body = payload(); body[axis][key] = value; cases.append(body)
        body = payload(); body['x_baseline'] = [.3,.1,.1]; cases.append(body)
        body = payload(); body['fixed_enrollment'] = {'control': 1_000_001, 'treatment': 1_000_001}; cases.append(body)
        body = payload(); body['fixed_enrollment']['control'] = 1003; cases.append(body)
        body = payload(); body['selected_scenario']['dropout']['control'] = .1; cases.append(body)
        body = payload(); body['effect_override'] = {'kind':'relative_risk','value':.5}; body['selected_scenario']['effect_override'] = {'kind':'relative_risk','value':.7}; cases.append(body)
        body = payload(); body['x_baseline'] = {'min': .2, 'max': math.nextafter(.2, 1), 'steps': 3}; cases.append(body)
        for body in cases:
            with self.subTest(body=body), patch.object(grid, 'stress_grid') as compute:
                response = self.post(body)
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn('error', response.json())
                compute.assert_not_called()

    def test_hash_stability_and_provenance_preservation(self):
        body = payload()
        body['provenance'] = {'control_event_rate': {'source':'manual_user'}}
        result = self.success(body)
        repeated = self.success(dict(reversed(list(body.items()))))
        self.assertEqual(result['inputs_hash'], repeated['inputs_hash'])
        self.assertEqual(result['provenance']['control_event_rate']['source'], 'manual_user')
        body['selected_scenario']['dropout'] = {'control': .14, 'treatment': .14}
        self.assertNotEqual(self.success(body)['inputs_hash'], result['inputs_hash'])

    def test_31_by_21_and_contract_maximum_dimensions(self):
        body = payload()
        for columns, rows in ((31,21), (grid.MAX_COLUMNS,grid.MAX_ROWS)):
            body['x_baseline']['steps'] = columns; body['y_dropout']['steps'] = rows
            result = self.success(body)
            self.assertEqual(len(result['power']), rows)
            self.assertEqual({len(row) for row in result['power']}, {columns})

    def test_registered_openapi_has_concrete_point_contour_and_metadata_types(self):
        schema = self.client.get('/openapi.json').json()
        operation = schema['paths']['/api/v1/scenarios/grid']['post']
        response = operation['responses']['200']['content']['application/json']['schema']['$ref'].split('/')[-1]
        props = schema['components']['schemas'][response]['properties']
        self.assertIn('$ref', props['planned_point'])
        self.assertIn('$ref', props['contour_segments']['items'])
        self.assertIn('$ref', props['power_curve']['items'])
        point = schema['components']['schemas'][props['planned_point']['$ref'].split('/')[-1]]
        self.assertIn('expected_evaluable_n', point['properties'])
        self.assertIn('analytic_delta', props)
        self.assertIn('software_versions', props)
        self.assertIn('$ref', props['diagnostics']['items'])
        diagnostic = schema['components']['schemas'][props['diagnostics']['items']['$ref'].split('/')[-1]]
        self.assertTrue({'code', 'field', 'method', 'severity'} <= set(diagnostic['properties']))
        self.assertIn('422', operation['responses'])

    def test_openapi_snapshot_matches_registered_app(self):
        snapshot_path = Path(__file__).resolve().parents[2] / 'contracts' / 'openapi.snapshot.json'
        self.assertEqual(json.loads(snapshot_path.read_text()), self.client.get('/openapi.json').json())

    def test_all_invalid_arr_domain_keeps_valid_off_grid_comparison(self):
        body = payload()
        body['planned_design']['effect'] = {'kind': 'absolute_risk_reduction', 'value': .05}
        body['x_baseline'] = {'min': .01, 'max': .04, 'steps': 3}
        result = self.success(body)
        self.assertEqual(result['invalid_cell_count'], 6)
        self.assertIsNone(result['worst_case_power'])
        self.assertIsNotNone(result['planned_point']['power'])
        self.assertIsNotNone(result['selected_point']['power'])
        self.assertAlmostEqual(result['analytic_delta'], result['selected_point']['power'] - result['planned_point']['power'])
        self.assertFalse(any('analytic delta are unavailable' in w for w in result['warnings']))

    def test_canonical_export_preserves_grid_metadata_and_comparison(self):
        body = payload()
        result = self.success(body)
        exported = ExportPayload(
            planned_design=body['planned_design'], fixed_enrollment=body['fixed_enrollment'],
            grid_result=result, exported_at=result['computed_at'],
        ).model_dump(mode='json')
        self.assertEqual(exported['grid_result'], result)


if __name__ == '__main__':
    unittest.main()
