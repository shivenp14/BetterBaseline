"""Standalone contract tests: python3 -m unittest discover -s backend/app/domain."""

import copy
import unittest
from uuid import UUID

from app.domain import compare_facts


def fact(id="before", artifact="protocol", key="endpoint.week", value=24, unit="week"):
    return dict(id=id, artifact_id=artifact, version_id="version", logical_key=key,
                label="Endpoint", value=value, unit=unit, source={})


class ComparisonTests(unittest.TestCase):
    def test_amendment_preserves_contract_and_inputs(self):
        before, after = [fact()], [fact(id="after", value=36)]
        original = copy.deepcopy((before, after))
        change, = compare_facts(before, after)
        self.assertEqual({k: v for k, v in change.items() if k != "id"}, {
            "artifact_id": "protocol", "logical_key": "endpoint.week",
            "before_fact_id": "before", "after_fact_id": "after",
            "before_value": 24, "after_value": 36, "kind": "modified",
            "before_unit": "week", "after_unit": "week",
        })
        self.assertEqual(UUID(change["id"]).version, 5)
        self.assertEqual((before, after), original)

    def test_safe_numeric_formatting(self):
        for value in (24.0, "24.00", " 2.4e1 ", "+24"):
            with self.subTest(value=value):
                self.assertEqual(compare_facts([fact()], [fact(value=value, unit=" week ")]), [])

    def test_no_unsafe_equivalence(self):
        for value, unit in ((True, "week"), ("week 24", "week"), (24, "Week"),
                            (168, "day"), (None, "week"), ("24,0", "week")):
            with self.subTest(value=value, unit=unit):
                self.assertEqual(compare_facts([fact()], [fact(value=value, unit=unit)])[0]["kind"], "modified")
        self.assertTrue(compare_facts([fact(value="text")], [fact(value=" text ")]))
        self.assertTrue(compare_facts([fact(value=0.3)], [fact(value=0.1 + 0.2)]))

    def test_added_removed_and_explicit_null(self):
        added, = compare_facts([], [fact(value=None)])
        removed, = compare_facts([fact(value=None)], [])
        self.assertEqual((added["kind"], added["before_fact_id"], added["after_fact_id"]), ("added", None, "before"))
        self.assertEqual((removed["kind"], removed["before_fact_id"], removed["after_fact_id"]), ("removed", "before", None))
        self.assertEqual(compare_facts([], []), [])

    def test_artifact_scope_and_stable_order(self):
        before = [fact(artifact="b"), fact(artifact="a")]
        after = [fact(id="b2", artifact="b", value=36), fact(id="a2", artifact="a", value=48)]
        expected = compare_facts(before, after)
        self.assertEqual([c["artifact_id"] for c in expected], ["a", "b"])
        self.assertEqual(compare_facts(list(reversed(before)), list(reversed(after))), expected)
        self.assertEqual(expected[0]["id"], compare_facts([before[1]], [fact(id="a3", artifact="a", value=48)])[0]["id"])

    def test_metadata_only_changes(self):
        replacement = fact(id="new")
        replacement.update(label="New label", source={"quote": "new"}, version_id="next")
        self.assertEqual(compare_facts([fact()], [replacement]), [])

    def test_units_preserved_including_unit_only_and_missing_sides(self):
        change, = compare_facts([fact(unit=" week ")], [fact(unit="day")])
        self.assertEqual((change["before_unit"], change["after_unit"]), (" week ", "day"))
        self.assertEqual(change["kind"], "modified")
        added, = compare_facts([], [fact()])
        removed, = compare_facts([fact()], [])
        self.assertEqual((added["before_unit"], added["after_unit"]), (None, "week"))
        self.assertEqual((removed["before_unit"], removed["after_unit"]), ("week", None))

    def test_null_and_empty_units_are_distinct(self):
        for old, new in ((None, ""), ("", None), (None, " ")):
            change, = compare_facts([fact(unit=old)], [fact(unit=new)])
            self.assertEqual(change["kind"], "modified")
            self.assertEqual((change["before_unit"], change["after_unit"]), (old, new))
        self.assertEqual(compare_facts([fact(unit="")], [fact(unit=" ")]), [])

    def test_ids_stable_across_reextraction_and_numeric_formatting(self):
        baseline, = compare_facts([fact()], [fact(id="after", value=36)])
        retry, = compare_facts([fact(id="retry-old", value="24.00", unit=" week ")],
                              [fact(id="retry-new", value="3.60e1")])
        self.assertEqual(baseline["id"], retry["id"])
        self.assertEqual(retry["before_fact_id"], "retry-old")
        self.assertEqual(retry["after_value"], "3.60e1")
        changed_value, = compare_facts([fact()], [fact(value=48)])
        changed_unit, = compare_facts([fact()], [fact(value=36, unit="day")])
        self.assertNotEqual(baseline["id"], changed_value["id"])
        self.assertNotEqual(baseline["id"], changed_unit["id"])

    def test_added_removed_ids_stable_and_kinds_distinct(self):
        for before, after in (([], [fact()]), ([fact()], [])):
            original, = compare_facts(before, after)
            retry, = compare_facts([dict(f, id="retry") for f in before],
                                  [dict(f, id="retry", value="24.0") for f in after])
            self.assertEqual(original["id"], retry["id"])
        added, = compare_facts([], [fact(value=None, unit=None)])
        removed, = compare_facts([fact(value=None, unit=None)], [])
        self.assertNotEqual(added["id"], removed["id"])

    def test_invalid_inputs_fail_instead_of_silently_matching(self):
        for before, after in (([fact(), fact(id="duplicate")], []), ([], [fact(), fact()])):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                compare_facts(before, after)
        for value in ([], {}, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                compare_facts([], [fact(value=value)])
        invalid = fact()
        del invalid["value"]
        with self.assertRaises(ValueError):
            compare_facts([invalid], [])


if __name__ == "__main__":
    unittest.main()
