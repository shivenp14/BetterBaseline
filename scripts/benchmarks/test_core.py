"""D6 public harness checks; timings have no performance thresholds."""
from copy import deepcopy
import json
import hashlib
import math
import statistics
import unittest

from core import PRESETS, ROOT, canonical, measure, prepare, validate_result, workload_parameters


class BenchmarkTests(unittest.TestCase):
    def inputs(self, preset="baseline-collapse-v1"):
        return json.loads((ROOT / "demo-data" / preset / "inputs.json").read_text())

    def test_all_presets_use_real_core_results(self):
        for preset in PRESETS:
            for workload in ("design", "grid", "monte-carlo"):
                with self.subTest(preset=preset, workload=workload):
                    inputs = self.inputs(preset)
                    result = prepare(workload, inputs)()
                    validate_result(workload, inputs, result)
                    canonical(result)
                    self.assertEqual(result, prepare(workload, inputs)())

    def test_reference_and_inflation_are_separate_counts(self):
        inputs = self.inputs()
        result = prepare("design", inputs)()
        self.assertEqual(result["evaluable_per_arm"], 903)
        inputs["planned_design"]["dropout"] = {"control": .1, "treatment": .1}
        inflated = prepare("design", inputs)()
        validate_result("design", inputs, inflated)
        self.assertEqual(inflated["evaluable_per_arm"], 903)
        self.assertEqual(inflated["enrolled_per_arm"], 1004)
        grid = prepare("grid", self.inputs())()
        self.assertAlmostEqual(grid["selected_point"]["power"], .470, places=3)

    def test_validation_rejects_shape_mask_and_curve_corruption(self):
        inputs = self.inputs()
        original = prepare("grid", inputs)()
        changed = deepcopy(original)
        changed["power"] = changed["power"][:-1]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate_result("grid", inputs, changed)
        changed = deepcopy(original)
        changed["invalid_mask"] = [[True] * 31 for _ in range(21)]
        with self.assertRaisesRegex(ValueError, "null/mask"):
            validate_result("grid", inputs, changed)
        changed = deepcopy(original)
        changed["power_curve"][0]["dropout"] = .123
        with self.assertRaisesRegex(ValueError, "curve"):
            validate_result("grid", inputs, changed)

    def test_measurements_retain_raw_samples_and_correct_p95(self):
        result = measure(lambda: {"value": .15})
        samples = result["raw_elapsed_ns"]
        self.assertEqual(len(samples), 30)
        self.assertEqual(result["excluded_warmups"], 3)
        self.assertEqual(result["p95_ms"], sorted(samples)[28] / 1e6)
        self.assertTrue(result["identical_results"])
        self.assertEqual(result["representative_result"], {"value": .15})

    def test_measurement_rejects_nonreplaying_outputs_and_short_runs(self):
        values = iter(range(100))
        with self.assertRaisesRegex(RuntimeError, "different"):
            measure(lambda: {"value": next(values)})
        with self.assertRaises(ValueError):
            measure(lambda: {}, runs=29)

    def test_retained_reports_are_auditable(self):
        for path in sorted((ROOT / "scripts/benchmarks/reports").glob("*.json")):
            with self.subTest(report=path.name):
                report = json.loads(path.read_text())
                measurement = report["measurement"]
                samples = measurement["raw_elapsed_ns"]
                self.assertGreaterEqual(len(samples), 30)
                self.assertEqual(len(samples), measurement["measured_runs"])
                self.assertEqual(measurement["median_ms"], statistics.median(samples) / 1e6)
                self.assertEqual(measurement["p95_ms"], sorted(samples)[math.ceil(.95 * len(samples)) - 1] / 1e6)
                digest = hashlib.sha256(canonical(measurement["representative_result"]).encode()).hexdigest()
                self.assertEqual(digest, measurement["result_sha256"])
                digest = hashlib.sha256(canonical(report["computation_parameters"]).encode()).hexdigest()
                self.assertEqual(digest, report["computation_sha256"])
                validate_result(report["workload"], report["inputs"], measurement["representative_result"])
                digest = hashlib.sha256((ROOT / "scripts/benchmarks/core.py").read_bytes()).hexdigest()
                self.assertEqual(digest, report["environment"]["harness_source_sha256"])

    def test_parameters_include_axes_method_and_seed_identity(self):
        inputs = self.inputs()
        grid = workload_parameters("grid", inputs)
        self.assertEqual(len(grid["x_baseline"]), 31)
        self.assertEqual(len(grid["y_dropout"]), 21)
        self.assertEqual(grid["method_version"], "1.0.0")
        mc = workload_parameters("monte-carlo", inputs)
        self.assertEqual(mc["fixture_inputs"]["simulation"], {"replicates": 10000, "seed": 42})


if __name__ == "__main__":
    unittest.main()
