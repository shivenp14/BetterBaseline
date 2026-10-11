"""Offline integrity checks; these are not statistical engine validation."""

import hashlib
import json
import math
from pathlib import Path
import unittest


DATA = Path(__file__).resolve().parents[2] / "demo-data"
CASES = {
    "baseline-collapse-v1": (0.0, .10, 0.0, 903, 903),
    "attrition-shock-v1": (.05, .20, .25, 951, 713),
    "stable-design-v1": (.05, .19, .06, 951, 893),
}


def read_json(path):
    def reject_constant(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


def leaves(value, pointer=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, pointer + "/" + key)
    else:
        yield pointer, value


class DemoPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = read_json(DATA / "index.json")
        cls.presets = {}
        for entry in cls.index["presets"]:
            manifest_path = DATA / entry["manifest"]
            manifest = read_json(manifest_path)
            folder = manifest_path.parent
            cls.presets[entry["preset_id"]] = (
                manifest, read_json(folder / manifest["inputs_file"]),
                read_json(folder / manifest["mock_response_file"]),
            )

    def test_json_and_versioned_discovery(self):
        self.assertEqual(self.index["schema_version"], 1)
        self.assertEqual(self.index["project"], "Better Baseline")
        self.assertEqual(len(self.index["presets"]), 3)
        self.assertEqual(set(self.presets), set(CASES))
        for path in DATA.rglob("*.json"):
            with self.subTest(path=path):
                read_json(path)
        for key, (manifest, _, mock) in self.presets.items():
            self.assertEqual(manifest["preset_id"], key)
            self.assertEqual(manifest["preset_version"], 1)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(mock["schema_version"], 1)
            self.assertEqual(mock["preset_id"], key)
            self.assertEqual(manifest["project"], "Better Baseline")

    def test_exact_playbook_inputs_and_fixed_enrollment(self):
        for key, (_, inputs, mock) in self.presets.items():
            with self.subTest(preset=key):
                planned_d, stress_p, stress_d, enrolled, _ = CASES[key]
                self.assertEqual(inputs["planned_design"], {
                    "model_version": "binary-v1", "control_event_rate": .20,
                    "effect": {"kind": "relative_risk", "value": .75},
                    "alpha": .05, "target_power": .80, "allocation_ratio": 1.0,
                    "dropout": {"control": planned_d, "treatment": planned_d},
                })
                self.assertEqual(inputs["stress_scenario"], {
                    "control_event_rate": stress_p,
                    "dropout": {"control": stress_d, "treatment": stress_d},
                    "effect_override": None,
                })
                self.assertEqual(inputs["fixed_enrollment"],
                                 {"control": enrolled, "treatment": enrolled})
                self.assertEqual(mock["design"]["enrolled_n"], inputs["fixed_enrollment"])
                self.assertEqual(inputs["simulation"], {"replicates": 10000, "seed": 42})

    def test_count_semantics_and_documented_reference(self):
        for key, (manifest, inputs, mock) in self.presets.items():
            with self.subTest(preset=key):
                d, _, stress_d, enrolled, retained = CASES[key]
                self.assertEqual(enrolled, math.ceil(903 / (1 - d)))
                self.assertEqual(retained, math.floor(enrolled * (1 - stress_d)))
                reference = manifest["reference_expectations"]
                self.assertEqual(reference["status"], "documented_reference_not_measured")
                self.assertEqual(reference["evaluable_n_per_arm"], 903)
                self.assertEqual(reference["planned_expected_retained_floor_per_arm"], 903)
                self.assertEqual(reference["stress_expected_retained_floor_per_arm"], retained)
                analytic = mock["point"]["analytic"]
                self.assertEqual(analytic["assumed_evaluable_n"],
                                 {"control": retained, "treatment": retained})
                self.assertEqual(analytic["retention_semantics"], "floor_of_expected_retained_count")
                self.assertEqual(mock["design"]["evaluable_n"], {"control": 903, "treatment": 903})
        manifest, _, mock = self.presets["baseline-collapse-v1"]
        self.assertEqual(manifest["reference_expectations"]["stress_analytic_power_approx"], .470)
        self.assertAlmostEqual(mock["point"]["analytic"]["conditional_power_approx"], .470)
        self.assertEqual(math.ceil(903 / .90), 1004)
        _, _, attrition = self.presets["attrition-shock-v1"]
        self.assertNotEqual(attrition["point"]["monte_carlo"]["mean_retained_control"], 713)

    def test_every_input_leaf_has_synthetic_provenance(self):
        for key, (manifest, inputs, _) in self.presets.items():
            with self.subTest(preset=key):
                expected = dict(leaves(inputs))
                records = manifest["provenance"]
                self.assertEqual(len(records), len(expected))
                self.assertEqual({r["field"]: r["value"] for r in records}, expected)
                for record in records:
                    self.assertEqual(record["origin"], "synthetic_preset")
                    self.assertIsNone(record["source_url"])
                    self.assertFalse(record["verified_by_user"])
                    self.assertTrue(record["source_location"].startswith("docs/"))
                    self.assertTrue(record["basis"])
                self.assertEqual(manifest["probability_units"], "fraction")
                self.assertEqual(manifest["scenario_origin"], "synthetic_preset")

    def test_hash_traces_identical_inputs_in_manifest_and_mock(self):
        for key, (manifest, inputs, mock) in self.presets.items():
            with self.subTest(preset=key):
                serialized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
                digest = "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()
                self.assertEqual(manifest["inputs_hash"], digest)
                self.assertEqual(mock["metadata"]["inputs_hash"], digest)

    def test_mock_results_cannot_be_mistaken_for_measured_snapshots(self):
        for manifest, _, mock in self.presets.values():
            self.assertEqual(manifest["contract_status"], "draft_pending_B1")
            self.assertEqual(mock["contract_status"], "draft_pending_B1")
            self.assertEqual(mock["result_status"], "illustrative_hand_authored")
            self.assertIn("illustrative", " ".join(mock["warnings"]))
            self.assertIn("not measured", " ".join(mock["point"]["warnings"]))
            for field in ("computed_at", "software_versions", "engine_commit"):
                self.assertIsNone(mock["metadata"][field])
            handoff = manifest["snapshot_requirements"]
            self.assertEqual(handoff["status"], "pending")
            self.assertTrue(handoff["actual_engine_functions_required"])
            self.assertTrue(handoff["record_software_versions"])
            self.assertTrue(handoff["record_engine_commit"])
            self.assertEqual(handoff["fixed_seed"], 42)

    def test_mc_split_error_and_random_aggregate_fields(self):
        for _, inputs, mock in self.presets.values():
            mc = mock["point"]["monte_carlo"]
            self.assertEqual(mc["result_status"], "illustrative_hand_authored")
            self.assertNotIn("mcse", mc)
            self.assertEqual(mc["invalid_test_policy"], "nonrejection_over_all_replicates")
            self.assertEqual(mc["replicates"], inputs["simulation"]["replicates"])
            self.assertEqual(mc["seed"], inputs["simulation"]["seed"])
            self.assertLessEqual(mc["significant_favorable_fraction"], mc["significant_two_sided_fraction"])
            for side in ("two_sided", "favorable"):
                fraction = mc[f"significant_{side}_fraction"]
                self.assertTrue(0 <= fraction <= 1)
                self.assertAlmostEqual(mc[f"mcse_{side}"], math.sqrt(fraction*(1-fraction)/mc["replicates"]))
            for arm, events in (("control", "mean_control_events"), ("treatment", "mean_treatment_events")):
                self.assertTrue(0 <= mc[events] <= mc[f"mean_retained_{arm}"] <= inputs["fixed_enrollment"][arm])

    def test_grid_axes_shape_mask_and_selected_point(self):
        for _, inputs, mock in self.presets.values():
            grid = mock["grid"]
            x, y = grid["x_baseline"], grid["y_dropout"]
            self.assertNotEqual(len(x), len(y))  # a transpose must be detectable
            self.assertEqual(grid["matrix_order"], "dropout_index,baseline_index")
            self.assertEqual(grid["target_power"], inputs["planned_design"]["target_power"])
            self.assertEqual(grid["method"], "cohen_h_normal_v1")
            self.assertIn("expected retained counts", grid["label"])
            self.assertEqual(len(grid["power"]), len(y))
            self.assertEqual(len(grid["invalid_mask"]), len(y))
            for row, mask in zip(grid["power"], grid["invalid_mask"]):
                self.assertEqual(len(row), len(x))
                self.assertEqual(len(mask), len(x))
                for power, invalid in zip(row, mask):
                    self.assertIs(type(invalid), bool)
                    self.assertEqual(power is None, invalid)
                    if power is not None:
                        self.assertTrue(0 <= power <= 1)
            scenario = inputs["stress_scenario"]
            self.assertEqual(grid["selected_point"], {
                "control_event_rate": scenario["control_event_rate"],
                "dropout": scenario["dropout"]["control"],
            })
            selected = grid["power"][y.index(scenario["dropout"]["control"])][x.index(scenario["control_event_rate"])]
            self.assertEqual(selected, mock["point"]["analytic"]["conditional_power_approx"])
            self.assertEqual(grid["frontier_points"], [])
            self.assertEqual(grid["frontier_status"], "not_computed_in_mock")


if __name__ == "__main__":
    unittest.main()
