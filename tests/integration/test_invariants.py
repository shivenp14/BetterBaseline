"""Fixture-mode checker regressions. No fixture is claimed as measured output."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from invariants import check_design, check_evaluation, check_export, check_grid

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    folder = ROOT / 'demo-data' / name
    request = json.loads((folder / 'inputs.json').read_text())
    mock = json.loads((folder / 'mock-response.json').read_text())
    manifest = json.loads((folder / 'manifest.json').read_text())
    # Explicitly hand-authored test witness. Never used as a production export.
    provenance = {item['field']: deepcopy(item) for item in manifest['provenance']}
    exported = dict(export_schema_version=1, planned_design=deepcopy(request['planned_design']),
                    fixed_enrollment=deepcopy(request['fixed_enrollment']),
                    stress_scenario=deepcopy(request['stress_scenario']),
                    evaluation_result=deepcopy(mock['point']), provenance=deepcopy(provenance))
    return request, mock, exported, provenance


class PipelineFixtureChecks(unittest.TestCase):
    def test_all_committed_presets_cross_boundary(self):
        index = json.loads((ROOT / 'demo-data/index.json').read_text())
        for entry in index['presets']:
            with self.subTest(preset=entry['preset_id']):
                request, mock, exported, provenance = fixture(entry['preset_id'])
                check_design(request['planned_design'], mock['design'])
                check_evaluation(request, mock['point'])
                check_grid(request, mock['point'], mock['grid'])
                check_export(request, mock['point'], exported, provenance)

    def test_reference_and_dropout_contract(self):
        request, mock, _, _ = fixture('baseline-collapse-v1')
        self.assertEqual(mock['design']['evaluable_n'], dict(control=903, treatment=903))
        self.assertAlmostEqual(mock['point']['analytic']['conditional_power_approx'], .470, delta=.005)
        planned, design = deepcopy(request['planned_design']), deepcopy(mock['design'])
        planned['dropout'] = dict(control=.10, treatment=.10)
        design['enrolled_n'] = dict(control=1004, treatment=1004)
        check_design(planned, design)
        design['enrolled_n']['control'] = 1003
        with self.assertRaisesRegex(AssertionError, 'inflation'):
            check_design(planned, design)

    def test_decimal_floor_and_zero_expected_retention_contract(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        req['simulation'] = None
        mock['point']['monte_carlo'] = None
        for enrolled, dropout, expected in ((50, .58, 21), (1, .90, 0)):
            req['fixed_enrollment'] = dict(control=enrolled, treatment=enrolled)
            req['stress_scenario']['dropout'] = dict(control=dropout, treatment=dropout)
            mock['point']['analytic']['assumed_evaluable_n'] = dict(control=expected, treatment=expected)
            mock['point']['analytic']['conditional_power_approx'] = None if expected == 0 else .47
            check_evaluation(req, mock['point'])
        mock['point']['analytic']['conditional_power_approx'] = 0
        with self.assertRaisesRegex(AssertionError, 'availability'):
            check_evaluation(req, mock['point'])

    def test_transpose_is_detected(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mock['grid']['power'] = list(map(list, zip(*mock['grid']['power'])))
        with self.assertRaisesRegex(AssertionError, 'transposed'):
            check_grid(req, mock['point'], mock['grid'])

    def test_null_mask_and_zero_are_distinct(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        grid = mock['grid']
        grid['invalid_mask'][1][2] = True
        grid['power'][1][2] = None
        grid['power'][1][1] = 0
        check_grid(req, mock['point'], grid)
        grid['power'][1][2] = 0
        with self.assertRaisesRegex(AssertionError, 'null'):
            check_grid(req, mock['point'], grid)

    def test_selected_point_drift_is_detected(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mock['grid']['power'][0][0] = .99
        with self.assertRaisesRegex(AssertionError, 'disagreement'):
            check_grid(req, mock['point'], mock['grid'])

    def test_conflated_expected_and_simulated_counts_are_detected(self):
        req, mock, _, _ = fixture('attrition-shock-v1')
        mock['point']['analytic']['assumed_evaluable_n']['control'] = mock['point']['monte_carlo']['mean_retained_control']
        with self.assertRaisesRegex(AssertionError, 'floor/count'):
            check_evaluation(req, mock['point'])

    def test_missing_mcse_split_is_detected(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mock['point']['monte_carlo']['mcse'] = .005
        with self.assertRaisesRegex(AssertionError, 'unsplit'):
            check_evaluation(req, mock['point'])

    def test_invalid_rejections_and_valid_only_mcse_are_detected(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mc = mock['point']['monte_carlo']
        mc['invalid_test_fraction'] = .75
        with self.assertRaisesRegex(AssertionError, 'rejections'):
            check_evaluation(req, mock['point'])
        mc['invalid_test_fraction'] = .25
        mc['mcse_two_sided'] *= (1/.75)**.5
        with self.assertRaisesRegex(AssertionError, 'all replicates'):
            check_evaluation(req, mock['point'])

    def test_all_invalid_nonrejection_and_disabled_simulation(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mc = mock['point']['monte_carlo']
        mc['invalid_test_fraction'] = 1
        for side in ('two_sided', 'favorable'):
            mc[f'significant_{side}_fraction'] = mc[f'mcse_{side}'] = 0
        check_evaluation(req, mock['point'])
        req['simulation'] = None
        with self.assertRaisesRegex(AssertionError, 'explicit null'):
            check_evaluation(req, mock['point'])
        mock['point']['monte_carlo'] = None
        check_evaluation(req, mock['point'])

    def test_provenance_and_export_mutations_are_detected(self):
        req, mock, exported, provenance = fixture('attrition-shock-v1')
        for mutation in ('provenance', 'fixed_enrollment', 'evaluation_result', 'planned_design'):
            with self.subTest(mutation=mutation):
                bad = deepcopy(exported)
                bad[mutation] = {}
                with self.assertRaises(AssertionError):
                    check_export(req, mock['point'], bad, provenance)
        bad = deepcopy(exported)
        next(iter(bad['provenance'].values()))['origin'] = 'protocol_curated'
        with self.assertRaisesRegex(AssertionError, 'relabeled'):
            check_export(req, mock['point'], bad, provenance)

    def test_seed_and_nonfinite_serialization_drift(self):
        req, mock, _, _ = fixture('baseline-collapse-v1')
        mock['point']['monte_carlo']['seed'] = 7
        with self.assertRaisesRegex(AssertionError, 'seed'):
            check_evaluation(req, mock['point'])
        mock['point']['monte_carlo']['seed'] = 42
        mock['point']['analytic']['conditional_power_approx'] = float('nan')
        with self.assertRaises(ValueError):
            check_evaluation(req, mock['point'])


if __name__ == '__main__':
    unittest.main()
