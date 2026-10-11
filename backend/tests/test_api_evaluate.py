"""Prospective acceptance tests for #65's real scenario-evaluation endpoint.

Run from the repo root after #64's registered scaffold and #56/#58's engines:
  PYTHONPATH=backend python3 -m unittest discover -s backend/tests \
      -p test_api_evaluate.py -v

The live suite intentionally fails if app.main or the real endpoint is absent;
there is no skip, stub response, or fixture fallback. Checker regression tests
can run independently while the shared router handoff is pending:
  PYTHONPATH=backend python3 -m unittest discover -s backend/tests \
      -p test_api_evaluate.py -k EvaluationAssertionTests -v

Metadata/provenance placement is pending #63/#64's final helper interfaces.
Tests require the issue's semantics while allowing metadata at the result or
response level. They do not replace schemas or edit shared bootstrap files.
"""

from copy import deepcopy
import importlib
import json
import math
import unittest


ENDPOINT = "/api/v1/scenarios/evaluate"


def request_payload(*, enrolled=903, baseline=.10, dropout=0.,
                    planned_dropout=0., simulation=True):
    return {
        "planned_design": {
            "model_version": "binary-v1", "control_event_rate": .20,
            "effect": {"kind": "relative_risk", "value": .75},
            "alpha": .05, "target_power": .80, "allocation_ratio": 1.,
            "dropout": {"control": planned_dropout, "treatment": planned_dropout},
        },
        "fixed_enrollment": {"control": enrolled, "treatment": enrolled},
        "stress_scenario": {
            "control_event_rate": baseline,
            "dropout": {"control": dropout, "treatment": dropout},
            "effect_override": None,
        },
        "simulation": {"replicates": 10_000, "seed": 42} if simulation else None,
    }


def assert_result_semantics(test, request, result):
    """Check transport/count/MC meanings without duplicating either engine."""
    # allow_nan=False catches nonfinite floats even if a JSON parser accepts them.
    json.dumps(result, allow_nan=False)
    test.assertEqual(result["model_version"], "binary-v1")
    analytic = result["analytic"]
    test.assertEqual(analytic["method"], "cohen_h_normal_v1")
    test.assertTrue(0 <= analytic["conditional_power_approx"] <= 1)
    for arm in ("control", "treatment"):
        count = math.floor(request["fixed_enrollment"][arm]
                           * (1 - request["stress_scenario"]["dropout"][arm]))
        test.assertEqual(analytic["assumed_evaluable_n"][arm], count)
        test.assertIs(type(analytic["assumed_evaluable_n"][arm]), int)
    if request["simulation"] is None:
        test.assertIn("monte_carlo", result)
        test.assertIsNone(result["monte_carlo"])
        return
    mc = result["monte_carlo"]
    test.assertEqual(mc["method"], "pooled_two_proportion_z_v1")
    test.assertEqual(mc["seed"], request["simulation"]["seed"])
    test.assertEqual(mc["replicates"], request["simulation"]["replicates"])
    test.assertNotIn("mcse", mc)
    test.assertTrue(0 <= mc["invalid_test_fraction"] <= 1)
    test.assertLessEqual(mc["significant_favorable_fraction"], mc["significant_two_sided_fraction"])
    for side in ("two_sided", "favorable"):
        fraction = mc[f"significant_{side}_fraction"]
        test.assertTrue(0 <= fraction <= 1)
        test.assertAlmostEqual(mc[f"mcse_{side}"],
                               math.sqrt(fraction*(1-fraction)/mc["replicates"]),
                               delta=1e-10)
    for arm, event_field in (("control", "mean_control_events"),
                              ("treatment", "mean_treatment_events")):
        test.assertTrue(0 <= mc[event_field] <= mc[f"mean_retained_{arm}"]
                        <= request["fixed_enrollment"][arm])


class EvaluationAssertionTests(unittest.TestCase):
    """Prove the pending endpoint's assertions catch transport regressions."""

    def setUp(self):
        # Explicitly hand-authored checker input; not a measured API snapshot.
        self.request = request_payload(enrolled=951, baseline=.20, dropout=.25,
                                       planned_dropout=.05)
        self.result = {
            "model_version": "binary-v1",
            "analytic": {"method": "cohen_h_normal_v1",
                         "conditional_power_approx": .70,
                         "assumed_evaluable_n": {"control": 713, "treatment": 713}},
            "monte_carlo": {
                "method": "pooled_two_proportion_z_v1",
                "significant_two_sided_fraction": .70,
                "significant_favorable_fraction": .69,
                "mcse_two_sided": math.sqrt(.70*.30/10000),
                "mcse_favorable": math.sqrt(.69*.31/10000),
                "invalid_test_fraction": 0., "replicates": 10000, "seed": 42,
                "mean_retained_control": 713.24, "mean_retained_treatment": 713.26,
                "mean_control_events": 142.6, "mean_treatment_events": 107.,
            },
        }

    def test_valid_checker_example(self):
        assert_result_semantics(self, self.request, self.result)

    def test_resizing_stress_enrollment_is_detected(self):
        self.result["analytic"]["assumed_evaluable_n"] = {"control": 903, "treatment": 903}
        with self.assertRaises(AssertionError):
            assert_result_semantics(self, self.request, self.result)

    def test_missing_split_mcse_is_detected(self):
        del self.result["monte_carlo"]["mcse_favorable"]
        with self.assertRaises(KeyError):
            assert_result_semantics(self, self.request, self.result)

    def test_mcse_using_valid_only_denominator_is_detected(self):
        mc = self.result["monte_carlo"]
        mc["invalid_test_fraction"] = .25
        mc["mcse_two_sided"] = math.sqrt(.70*.30/7500)
        with self.assertRaises(AssertionError):
            assert_result_semantics(self, self.request, self.result)

    def test_nonfinite_json_is_detected(self):
        self.result["monte_carlo"]["mean_control_events"] = float("nan")
        with self.assertRaises(ValueError):
            assert_result_semantics(self, self.request, self.result)

    def test_disabled_simulation_must_be_explicitly_null(self):
        self.request["simulation"] = None
        with self.assertRaises(AssertionError):
            assert_result_semantics(self, self.request, self.result)
        self.result["monte_carlo"] = None
        assert_result_semantics(self, self.request, self.result)


class ScenarioEvaluationAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        try:
            cls.application = importlib.import_module("app.main").app
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "#65 live acceptance requires #64's app.main scaffold and the "
                "registered evaluation router; no fixture fallback is permitted."
            ) from error
        cls.client = TestClient(cls.application)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def evaluate(self, payload):
        response = self.client.post(ENDPOINT, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        assert_result_semantics(self, payload, result)
        return result

    def assert_error(self, payload):
        response = self.client.post(ENDPOINT, json=payload)
        self.assertEqual(response.status_code, 422, response.text)
        error = response.json()["error"]
        self.assertIsInstance(error["code"], str)
        self.assertTrue(error["code"])
        self.assertIsInstance(error["message"], str)
        self.assertTrue(error["message"])
        self.assertIn("field", error)
        self.assertIsInstance(error["recoverable"], bool)
        self.assertNotIn("Traceback", response.text)

    def test_baseline_collapse_reference_and_immutable_request(self):
        payload = request_payload()
        before = deepcopy(payload)
        result = self.evaluate(payload)
        self.assertAlmostEqual(result["analytic"]["conditional_power_approx"], .470, delta=.005)
        self.assertEqual(payload, before)

    def test_stress_changes_keep_enrollment_frozen(self):
        payload = request_payload(enrolled=951, baseline=.20, dropout=.05,
                                  planned_dropout=.05)
        planned = deepcopy(payload["planned_design"])
        first = self.evaluate(payload)
        payload["stress_scenario"]["dropout"] = {"control": .25, "treatment": .25}
        second = self.evaluate(payload)
        self.assertEqual(first["analytic"]["assumed_evaluable_n"]["control"], 903)
        self.assertEqual(second["analytic"]["assumed_evaluable_n"]["control"], 713)
        self.assertLess(second["analytic"]["conditional_power_approx"],
                        first["analytic"]["conditional_power_approx"])
        self.assertEqual(payload["fixed_enrollment"], {"control": 951, "treatment": 951})
        self.assertEqual(payload["planned_design"], planned)
        payload["stress_scenario"]["control_event_rate"] = .10
        third = self.evaluate(payload)
        self.assertEqual(third["analytic"]["assumed_evaluable_n"], second["analytic"]["assumed_evaluable_n"])
        self.assertLess(third["analytic"]["conditional_power_approx"],
                        second["analytic"]["conditional_power_approx"])

    def test_api_mc_values_match_real_seeded_primitive(self):
        from app.statistics.simulation import simulate_binary
        payload = request_payload(enrolled=951, baseline=.20, dropout=.25,
                                  planned_dropout=.05)
        result = self.evaluate(payload)
        expected = simulate_binary(951, 951, .20, .15, .25, .25, reps=10000, seed=42)
        for field in ("significant_two_sided_fraction", "significant_favorable_fraction",
                      "mcse_two_sided", "mcse_favorable", "invalid_test_fraction",
                      "mean_retained_control", "mean_retained_treatment",
                      "mean_control_events", "mean_treatment_events", "replicates", "seed"):
            with self.subTest(field=field):
                self.assertAlmostEqual(result["monte_carlo"][field], expected[field], delta=1e-10)

    def test_repeated_requests_reproduce_numeric_results(self):
        payload = request_payload()
        first = self.evaluate(payload)
        second = self.evaluate(payload)
        self.assertEqual(first["analytic"], second["analytic"])
        self.assertEqual(first["monte_carlo"], second["monte_carlo"])

    def test_explicit_fast_analytic_request_omits_simulation(self):
        result = self.evaluate(request_payload(simulation=False))
        self.assertIsNone(result["monte_carlo"])
        self.assertAlmostEqual(result["analytic"]["conditional_power_approx"], .470, delta=.005)

    def test_invalid_arr_is_structured_error_not_clipped(self):
        payload = request_payload(baseline=.04)
        payload["planned_design"]["effect"] = {"kind": "absolute_risk_reduction", "value": .05}
        self.assert_error(payload)
        payload = request_payload(baseline=.10)
        payload["stress_scenario"]["effect_override"] = {"kind": "absolute_risk_reduction", "value": .10}
        self.assert_error(payload)

    def test_p0_symmetry_and_invalid_counts(self):
        for count in (0, -1, True, 903.5, "903"):
            payload = request_payload()
            payload["fixed_enrollment"] = {"control": count, "treatment": count}
            with self.subTest(count=count):
                self.assert_error(payload)
        payload = request_payload()
        payload["fixed_enrollment"]["treatment"] = 902
        self.assert_error(payload)
        for section in ("planned_design", "stress_scenario"):
            payload = request_payload()
            payload[section]["dropout"] = {"control": .05, "treatment": .10}
            self.assert_error(payload)

    def test_strict_replication_and_seed_limits(self):
        for field, values in {"replicates": (0, 100001, 100.5, True, "10000"),
                              "seed": (-1, 2**32, 42.5, True, "42")}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = request_payload()
                    payload["simulation"][field] = value
                    self.assert_error(payload)

    def test_metadata_records_versions_and_rng(self):
        result = self.evaluate(request_payload())
        metadata = result["metadata"]
        self.assertTrue(metadata["computed_at"])
        self.assertTrue(metadata["inputs_hash"])
        # Support a shared response-level record or per-result records.
        records = [metadata, result["analytic"], result["monte_carlo"]]
        versions = {}
        for record in records:
            versions.update(record.get("software_versions", {}))
        for package in ("python", "numpy", "scipy", "statsmodels"):
            self.assertIsInstance(versions[package], str)
            self.assertTrue(versions[package])
        rngs = [record.get("rng") for record in records if record.get("rng")]
        self.assertIn("numpy.random.PCG64", rngs)


if __name__ == "__main__":
    unittest.main()
