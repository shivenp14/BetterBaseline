"""Supported, warned, rejected, and real primitive diagnostic regressions."""

import json
import unittest

from app.statistics.analytic import analytic_power
from app.statistics.diagnostics import analytic_diagnostics, simulation_diagnostics
from app.statistics.inputs import expected_retained_count
from app.statistics.simulation import simulate_binary


class DiagnosticTests(unittest.TestCase):
    def analytic(self, **overrides):
        args = dict(p_control=.2, p_treatment=.15, n_control_evaluable=903,
                    n_treatment_evaluable=903)
        args.update(overrides)
        return analytic_diagnostics(**args)

    def simulation(self, **overrides):
        args = dict(n_c=903, n_t=903, p_c=.2, p_t=.15, d_c=0., d_t=0.)
        args.update(overrides)
        return simulation_diagnostics(**args)

    def codes(self, result, severity=None):
        return [d["code"] for d in result["diagnostics"]
                if severity is None or d["severity"] == severity]

    def assert_json(self, result):
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        for entry in result["diagnostics"]:
            self.assertTrue({"code", "severity", "field", "method", "message"} <= entry.keys())
        self.assertNotIn("power", result)

    def test_supported_regimes_and_interpretation(self):
        for result in (self.analytic(), self.simulation()):
            self.assertTrue(result["valid"])
            self.assertEqual(self.codes(result, "warning"), [])
            self.assertIn("CONDITIONAL_POWER_ONLY", self.codes(result))
            message = result["diagnostics"][0]["message"]
            for term in ("conditional", "assumptions", "efficacy", "clinical recommendation"):
                self.assertIn(term, message)
            self.assert_json(result)
        self.assertIn("DISTINCT_METHOD_APPROXIMATIONS", self.codes(self.simulation()))

    def test_null_is_supported_not_a_degenerate_test(self):
        result = self.analytic(p_treatment=.2)
        self.assertTrue(result["valid"])
        self.assertEqual(self.codes(result, "warning"), [])
        self.assertAlmostEqual(analytic_power(.2, .2, 903, 903).power, .05)

    def test_count_threshold_is_strict_and_each_arm_outcome_is_named(self):
        # Exactly five events and five nonevents per arm is not below five.
        result = self.analytic(p_control=.5, p_treatment=.5,
                               n_control_evaluable=10, n_treatment_evaluable=10)
        self.assertEqual(self.codes(result, "warning"), [])
        result = self.analytic(p_control=.49, p_treatment=.51,
                               n_control_evaluable=10, n_treatment_evaluable=10)
        warnings = [d for d in result["diagnostics"] if d["code"] == "LOW_EXPECTED_COUNT"]
        self.assertTrue(result["valid"])
        self.assertEqual([(d["arm"], d["outcome"]) for d in warnings],
                         [("control", "events"), ("treatment", "non_events")])
        self.assertEqual([d["field"] for d in warnings], ["p_control", "p_treatment"])
        for entry in warnings:
            self.assertAlmostEqual(entry["expected_count"], 4.9)
            self.assertEqual(entry["threshold"], 5)
            self.assertEqual(entry["count_basis"], "evaluable_count")
            self.assertIn("Cohen’s-h", entry["message"])
        self.assert_json(result)

    def test_boundary_warnings_are_separate_from_count_warnings(self):
        for rate in (.001, .01, .99, .999):
            with self.subTest(rate=rate):
                result = self.analytic(p_control=rate, p_treatment=rate,
                                       n_control_evaluable=100_000,
                                       n_treatment_evaluable=100_000)
                self.assertTrue(result["valid"])
                self.assertEqual(self.codes(result, "warning"),
                                 ["NEAR_BOUNDARY_PROBABILITY"] * 2)
        self.assertEqual(self.codes(self.analytic(p_control=.011, p_treatment=.989), "warning"), [])

    def test_low_count_cells_keep_real_analytic_values(self):
        result = self.analytic(p_control=.001, p_treatment=.0005,
                               n_control_evaluable=10, n_treatment_evaluable=10)
        self.assertTrue(result["valid"])
        self.assertIn("LOW_EXPECTED_COUNT", self.codes(result))
        self.assertGreater(analytic_power(.001, .0005, 10, 10).power, 0)

    def test_simulation_uses_unfloored_expected_retention(self):
        # Analytic floor gives 9*.53=4.77; expected random retention gives
        # 9.5*.53=5.035, a distinct threshold outcome.
        count = expected_retained_count(10, .05)
        self.assertEqual(count, 9)
        analytic = self.analytic(p_control=.53, p_treatment=.53,
                                 n_control_evaluable=count, n_treatment_evaluable=count)
        simulated = self.simulation(n_c=10, n_t=10, p_c=.53, p_t=.53, d_c=.05, d_t=.05)
        a_events = [d for d in analytic["diagnostics"]
                    if d["code"] == "LOW_EXPECTED_COUNT" and d["outcome"] == "events"]
        s_events = [d for d in simulated["diagnostics"]
                    if d["code"] == "LOW_EXPECTED_COUNT" and d["outcome"] == "events"]
        self.assertEqual(len(a_events), 2)
        self.assertEqual(s_events, [])
        warnings = [d for d in simulated["diagnostics"] if d["code"] == "LOW_EXPECTED_COUNT"]
        self.assertEqual(len(warnings), 2)
        for d in warnings:
            self.assertEqual(d["count_basis"], "expected_random_retention")
            self.assertAlmostEqual(d["expected_count"], 9.5*.47)
            self.assertIn("pooled-z", d["message"])
            self.assertEqual(d["field"], f"{d['arm']}_event_rate")

    def test_zero_analytic_count_is_explicit_error_without_numeric_power(self):
        for arm in ("control", "treatment"):
            result = self.analytic(**{f"n_{arm}_evaluable": 0})
            self.assertFalse(result["valid"])
            self.assertEqual(self.codes(result), ["ZERO_EVALUABLE_COUNT"])
            self.assertEqual(result["diagnostics"][0]["field"], f"n_{arm}_evaluable")
            self.assert_json(result)

    def test_invalid_probabilities_and_alpha_are_json_safe_not_clipped(self):
        for helper, fields in ((self.analytic, ("p_control", "p_treatment", "alpha")),
                               (self.simulation, ("p_c", "p_t", "alpha", "d_c"))):
            for field in fields:
                values = [-.1, 1, float("nan"), float("inf"), True, "0.2", None, object()]
                if field != "d_c":
                    values.append(0)
                for value in values:
                    with self.subTest(field=field, value=value):
                        result = helper(**{field: value})
                        self.assertFalse(result["valid"])
                        self.assertEqual(self.codes(result), ["INVALID_MODEL_INPUT"])
                        self.assert_json(result)

    def test_count_validation_and_unsupported_models(self):
        for count in (-1, 1.5, True, "10", 10**400):
            for result in (self.analytic(n_control_evaluable=count, n_treatment_evaluable=count),
                           self.simulation(n_c=count, n_t=count)):
                self.assertFalse(result["valid"])
                self.assert_json(result)
        for result in (self.analytic(n_treatment_evaluable=902),
                       self.simulation(n_t=902), self.simulation(d_c=.1),
                       self.analytic(method="exact"), self.simulation(method="exact"),
                       self.analytic(method=object())):
            self.assertFalse(result["valid"])
            self.assertEqual(self.codes(result), ["UNSUPPORTED_MODEL"])
            self.assert_json(result)
        self.assertFalse(self.simulation(n_c=1_000_001, n_t=1_000_001)["valid"])
        self.assertTrue(self.simulation(n_c=1_000_000, n_t=1_000_000)["valid"])

    def test_observed_invalid_frequency_is_optional_not_invented(self):
        result = self.simulation(n_c=1, n_t=1, p_c=.001, p_t=.001)
        self.assertTrue(result["valid"])
        self.assertNotIn("INVALID_SIMULATED_TESTS", self.codes(result))
        self.assertFalse(any("invalid_test_fraction" in d for d in result["diagnostics"]))
        result = self.simulation(invalid_test_fraction=0, replicates=10)
        self.assertNotIn("INVALID_SIMULATED_TESTS", self.codes(result))

    def test_partial_and_all_invalid_runs_disclose_denominator_policy(self):
        for fraction, code in ((.75, "INVALID_SIMULATED_TESTS"),
                               (1., "ALL_SIMULATED_TESTS_INVALID")):
            result = self.simulation(invalid_test_fraction=fraction, replicates=4)
            self.assertTrue(result["valid"])
            entry = result["diagnostics"][-1]
            self.assertEqual(entry["code"], code)
            self.assertEqual(entry["invalid_test_fraction"], fraction)
            self.assertEqual(entry["replicates"], 4)
            self.assertEqual(entry["invalid_test_policy"], "nonrejection_over_all_replicates")
            self.assertEqual(entry["field"], "invalid_test_fraction")
            self.assert_json(result)

    def test_invalid_observed_diagnostic_inputs_rejected(self):
        cases = [dict(invalid_test_fraction=value, replicates=4)
                 for value in (-.1, 1.1, float("nan"), float("inf"), True, "0.1")]
        cases += [dict(invalid_test_fraction=.5, replicates=value)
                  for value in (0, 100_001, True, 4., "4")]
        cases += [dict(invalid_test_fraction=.5), dict(replicates=4)]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = self.simulation(**overrides)
                self.assertFalse(result["valid"])
                self.assert_json(result)

    def test_real_simulation_handoff_and_deterministic_serialization(self):
        simulated = simulate_binary(1, 1, .2, .15, .9, .9, reps=1000, seed=42)
        overrides = dict(n_c=1, n_t=1, p_c=.2, p_t=.15, d_c=.9, d_t=.9,
                         invalid_test_fraction=simulated["invalid_test_fraction"],
                         replicates=simulated["replicates"])
        first = self.simulation(**overrides)
        self.assertGreater(simulated["invalid_test_fraction"], .95)
        self.assertIn("INVALID_SIMULATED_TESTS", self.codes(first))
        self.assertIn("LOW_EXPECTED_COUNT", self.codes(first))
        self.assertEqual(first["diagnostics"][-1]["invalid_test_fraction"],
                         simulated["invalid_test_fraction"])
        self.assertEqual(json.dumps(first, sort_keys=True, allow_nan=False),
                         json.dumps(self.simulation(**overrides), sort_keys=True, allow_nan=False))
        self.assert_json(first)


if __name__ == "__main__":
    unittest.main()
