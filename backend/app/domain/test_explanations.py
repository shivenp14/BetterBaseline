"""Evidence-backed amendment walkthrough and edge cases for #32."""

import copy
import unittest

from app.domain import assess_impact, compare_facts
from test_impact import edge, fact


def source(identifier, locator, quote):
    return dict(fragment_id=identifier, locator=locator, quote=quote)


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(fact("old", "protocol"), label="Assessment week",
                        source=source("old-fragment", "paragraph 1", "Assessment at week 24."))
        self.new = dict(fact("new", "protocol", 36), label="Assessment week",
                        source=source("new-fragment", "paragraph 1", "Assessment at week 36."))
        self.schedule = dict(fact("schedule"), label="Visit schedule",
                             source=source("schedule-fragment", "row 2", "Visit at week 24."))
        self.analysis = dict(fact("analysis"), label="Analysis result",
                             source=source("analysis-fragment", "table 1", "Derived result."))
        self.facts = [self.old, self.new, self.schedule, self.analysis, fact("report")]
        self.edges = [dict(edge("schedule-edge", "old", "schedule"), evidence=[self.schedule["source"]]),
                      dict(edge("analysis-edge", "schedule", "analysis"), relationship="calculated_from"),
                      edge("pinned-report", "analysis", "report", tracking="pinned")]
        self.changes = compare_facts([self.old], [self.new])
        self.artifacts = {"analysis": "analysis_result"}

    def test_walkthrough_contains_change_target_path_action_and_sources(self):
        original = copy.deepcopy((self.changes, self.facts, self.edges))
        findings = assess_impact(self.changes, self.facts, self.edges, artifact_lookup=self.artifacts)
        self.assertEqual({f["affected_fact_id"] for f in findings}, {"schedule", "analysis"})
        finding = next(f for f in findings if f["affected_fact_id"] == "analysis")
        for text in ('24 [unit: "week"]', '36 [unit: "week"]', "Analysis result (analysis)",
                     "schedule-edge", "analysis-edge", "calculated_from", "Request reanalysis",
                     "old-fragment at paragraph 1", "schedule-fragment at row 2"):
            self.assertIn(text, finding["explanation"])
        self.assertEqual(finding["sources"], [self.old["source"], self.new["source"],
                                              self.schedule["source"], self.analysis["source"]])
        self.assertEqual((self.changes, self.facts, self.edges), original)
        finding["sources"][0]["quote"] = "changed by consumer"
        self.assertEqual(self.old["source"]["quote"], "Assessment at week 24.")

    def test_added_and_removed_facts_explain_absence_and_link_review(self):
        added, = assess_impact(compare_facts([], [self.new]), [self.new], [])
        self.assertIn("Added Assessment week", added["explanation"])
        self.assertIn("No established dependency path", added["explanation"])
        self.assertEqual(added["sources"], [self.new["source"]])
        removed = assess_impact(compare_facts([self.old], []), self.facts, self.edges)
        self.assertIn("Removed Assessment week", removed[0]["explanation"])
        self.assertIn('previously 24 [unit: "week"]', removed[0]["explanation"])

    def test_unit_only_change_and_explicit_null(self):
        replacement = dict(self.new, value=24, unit="day")
        findings = assess_impact(compare_facts([self.old], [replacement]), self.facts, self.edges)
        self.assertIn('24 [unit: "week"] to 24 [unit: "day"]', findings[0]["explanation"])
        added, = assess_impact(compare_facts([], [dict(self.new, value=None)]), [self.new], [])
        self.assertIn('null [unit: "week"]', added["explanation"])

    def test_missing_evidence_is_explicit_and_not_invented(self):
        old, new, dependent = fact("old", "protocol"), fact("new", "protocol", 36), fact("dependent")
        finding, = assess_impact(compare_facts([old], [new]), [old, dependent], [edge("e", "old", "dependent")])
        self.assertEqual(finding["sources"], [])
        self.assertIn("Source references are unavailable", finding["explanation"])
        self.assertIn("replacement fact snapshot was not supplied", finding["explanation"])

    def test_regeneration_and_input_order_preserve_explanations(self):
        expected = assess_impact(self.changes, self.facts, self.edges, artifact_lookup=self.artifacts)
        self.assertEqual(assess_impact(reversed(self.changes), reversed(self.facts), reversed(self.edges),
                                      artifact_lookup=self.artifacts), expected)

    def test_action_and_explanation_use_same_alternate_path(self):
        edges = self.edges + [dict(edge("a-direct", "old", "analysis"), relationship="describes")]
        finding = next(f for f in assess_impact(self.changes, self.facts, edges, artifact_lookup=self.artifacts)
                       if f["affected_fact_id"] == "analysis")
        self.assertEqual(finding["path_edge_ids"], ["schedule-edge", "analysis-edge"])
        self.assertIn("analysis-edge", finding["explanation"])
        self.assertNotIn("a-direct", finding["explanation"])
        self.assertIn("Request reanalysis", finding["explanation"])


if __name__ == "__main__":
    unittest.main()
