"""Real Monte Carlo checks plus exact invalid-denominator regressions."""

import json
import math
import unittest
from unittest.mock import Mock, patch

import numpy as np
from scipy.stats import norm

from app.statistics.errors import StatisticalInputError
from app.statistics.simulation import simulate_binary


class SimulationTests(unittest.TestCase):
    def run_case(self, **overrides):
        args = dict(n_c=903, n_t=903, p_c=.10, p_t=.075, d_c=0., d_t=0.)
        args.update(overrides)
        return simulate_binary(**args)

    def test_repeatability_defaults_and_metadata(self):
        first = self.run_case()
        second = self.run_case()
        self.assertEqual(json.dumps(first, sort_keys=True, allow_nan=False),
                         json.dumps(second, sort_keys=True, allow_nan=False))
        self.assertEqual(first["replicates"], 10_000)
        self.assertEqual(first["seed"], 42)
        self.assertEqual(first["method"], "pooled_two_proportion_z_v1")
        self.assertEqual(first["rng"], "numpy.random.PCG64")
        self.assertEqual(set(first["software_versions"]), {"python", "numpy", "scipy"})
        self.assertTrue(all(first["software_versions"].values()))
        self.assertNotIn("mcse", first)
        self.assertNotEqual(first, self.run_case(seed=43))

    def test_local_rng_preserves_global_numpy_state(self):
        before = np.random.get_state()
        self.run_case()
        after = np.random.get_state()
        self.assertEqual(before[0], after[0])
        np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[2:], after[2:])

    def test_null_two_sided_and_favorable_have_separate_mcse(self):
        result = self.run_case(n_c=5000, n_t=5000, p_c=.20, p_t=.20, reps=100_000)
        self.assertLess(abs(result["significant_two_sided_fraction"] - .05),
                        4 * result["mcse_two_sided"])
        self.assertLess(abs(result["significant_favorable_fraction"] - .025),
                        4 * result["mcse_favorable"])
        self.assertGreater(result["mcse_two_sided"], result["mcse_favorable"])

    def test_alternative_near_independent_cohen_h_reference(self):
        # Independent approximation, not another implementation of pooled-z MC.
        # Allow 4 MCSE + .02 for the distinct analytic/test approximations.
        for p_c, p_t in ((.10, .075), (.20, .15)):
            with self.subTest(p_c=p_c):
                h = 2 * (math.asin(math.sqrt(p_c)) - math.asin(math.sqrt(p_t)))
                shift = h * math.sqrt(903 / 2)
                cutoff = norm.isf(.05 / 2)
                analytic = norm.sf(cutoff - shift) + norm.cdf(-cutoff - shift)
                result = self.run_case(p_c=p_c, p_t=p_t, reps=100_000)
                self.assertLess(abs(result["significant_two_sided_fraction"] - analytic),
                                4 * result["mcse_two_sided"] + .02)
                if p_c == .10:
                    self.assertAlmostEqual(analytic, .470, delta=.005)

    def test_random_retention_and_event_moments(self):
        enrollment, dropout, reps = 951, .25, 100_000
        result = self.run_case(n_c=enrollment, n_t=enrollment, p_c=.20, p_t=.15,
                               d_c=dropout, d_t=dropout, reps=reps)
        retained_se = math.sqrt(enrollment * (1-dropout) * dropout / reps)
        for arm, event_rate, event_field in (("control", .20, "mean_control_events"),
                                            ("treatment", .15, "mean_treatment_events")):
            with self.subTest(arm=arm):
                self.assertLess(abs(result[f"mean_retained_{arm}"] - enrollment*(1-dropout)),
                                4*retained_se)
                # Marginal events have probability (1-d)*p per enrolled subject.
                q = (1-dropout)*event_rate
                event_se = math.sqrt(enrollment*q*(1-q)/reps)
                self.assertLess(abs(result[event_field] - enrollment*q), 4*event_se)
                self.assertNotEqual(result[f"mean_retained_{arm}"], math.floor(enrollment*(1-dropout)))
        self.assertNotEqual(result["mean_retained_control"], result["mean_retained_treatment"])

    def test_no_dropout_retains_all_enrolled(self):
        result = self.run_case()
        self.assertEqual(result["mean_retained_control"], 903)
        self.assertEqual(result["mean_retained_treatment"], 903)
        self.assertEqual(result["invalid_test_fraction"], 0)

    def test_exact_invalid_denominator_and_draw_order(self):
        # Empty control, empty treatment, zero-event variance, valid rejection.
        r_c = np.array([0, 10, 10, 10])
        r_t = np.array([10, 0, 10, 10])
        x_c = np.array([0, 2, 0, 10])
        x_t = np.array([0, 0, 0, 0])
        generator = Mock()
        generator.binomial.side_effect = [r_c, r_t, x_c, x_t]
        with patch("app.statistics.simulation.np.random.Generator", return_value=generator):
            result = self.run_case(n_c=10, n_t=10, d_c=.25, d_t=.25, reps=4)
        calls = generator.binomial.call_args_list
        self.assertEqual(calls[0].args, (10, .75))
        self.assertEqual(calls[0].kwargs, {"size": 4})
        self.assertEqual(calls[1].args, (10, .75))
        self.assertIs(calls[2].args[0], r_c)
        self.assertEqual(calls[2].args[1], .10)
        self.assertIs(calls[3].args[0], r_t)
        self.assertEqual(calls[3].args[1], .075)
        self.assertEqual(result["invalid_test_fraction"], .75)
        self.assertEqual(result["significant_two_sided_fraction"], .25)
        self.assertEqual(result["significant_favorable_fraction"], .25)
        self.assertEqual(result["invalid_test_policy"], "nonrejection_over_all_replicates")
        for field in ("mcse_two_sided", "mcse_favorable"):
            self.assertAlmostEqual(result[field], math.sqrt(.25*.75/4))
        json.dumps(result, allow_nan=False)

    def test_all_degenerate_cases_are_finite_nonrejections(self):
        for retained, events in ((0, 0), (10, 0), (10, 10)):
            with self.subTest(retained=retained, events=events):
                generator = Mock()
                generator.binomial.side_effect = [np.full(4, v) for v in (retained, retained, events, events)]
                with patch("app.statistics.simulation.np.random.Generator", return_value=generator):
                    result = self.run_case(n_c=10, n_t=10, reps=4)
                self.assertEqual(result["invalid_test_fraction"], 1)
                for field in ("significant_two_sided_fraction", "significant_favorable_fraction",
                              "mcse_two_sided", "mcse_favorable"):
                    self.assertEqual(result[field], 0)
                json.dumps(result, allow_nan=False)

    def test_rare_small_real_trials_disclose_invalid_tests(self):
        with np.errstate(all="raise"):
            result = self.run_case(n_c=1, n_t=1, p_c=.20, p_t=.15, d_c=.90, d_t=.90)
        self.assertGreater(result["invalid_test_fraction"], .95)
        self.assertIn("Undefined tests count as nonrejections over all replicates.", result["warnings"])
        self.assertTrue(any("below 5" in warning for warning in result["warnings"]))
        json.dumps(result, allow_nan=False)

    def test_unfavorable_effect_does_not_count_as_favorable(self):
        result = self.run_case(p_c=.075, p_t=.10, reps=100_000)
        self.assertGreater(result["significant_two_sided_fraction"], .40)
        self.assertLess(result["significant_favorable_fraction"], .001)

    def test_strict_replicate_and_seed_bounds(self):
        for field, values in {
            "reps": [0, -1, 100_001, 1.5, 10_000.0, True, "10000", None],
            "seed": [-1, 2**32, 42.0, True, "42", None],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with patch("app.statistics.simulation.np.random.Generator") as generator:
                        with self.assertRaises(StatisticalInputError) as failure:
                            self.run_case(**{field: value})
                        self.assertEqual(failure.exception.field, "replicates" if field == "reps" else "seed")
                        generator.assert_not_called()
        for seed in (0, 2**32-1):
            result = self.run_case(reps=1, seed=seed)
            self.assertEqual(result["replicates"], 1)
            self.assertEqual(result["seed"], seed)
            json.dumps(result, allow_nan=False)

    def test_invalid_probabilities_alpha_and_p0_inputs(self):
        cases = [{field: value} for field in ("p_c", "p_t", "alpha")
                 for value in (0, 1, -.1, float("nan"), float("inf"), True, "0.2")]
        cases += [{"d_c": value, "d_t": value}
                  for value in (-.1, 1, float("nan"), float("inf"), True, "0.1")]
        cases += [{"n_c": value, "n_t": value} for value in (0, -1, 1.0, True, "10", 1_000_001)]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with patch("app.statistics.simulation.np.random.Generator") as generator:
                    with self.assertRaises(StatisticalInputError):
                        self.run_case(**overrides)
                    generator.assert_not_called()
        for overrides in ({"n_c": 902}, {"d_c": .1, "d_t": .2}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(StatisticalInputError) as failure:
                    self.run_case(**overrides)
                self.assertEqual(failure.exception.code, "UNSUPPORTED_MODEL")

    def test_tiny_alpha_does_not_underflow_into_spurious_rejection(self):
        result = self.run_case(alpha=5e-324)
        self.assertEqual(result["significant_two_sided_fraction"], 0)
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
