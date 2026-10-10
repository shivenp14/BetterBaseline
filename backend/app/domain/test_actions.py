"""Action selection against a source→result→report fixture."""

import copy
import unittest

from app.domain import assess_impact, compare_facts
from app.domain.actions import impact_action
from test_impact import edge, fact


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.old = fact("old", "protocol")
        self.new = fact("new", "protocol", 36)
        self.changes = compare_facts([self.old], [self.new])
        self.facts = [self.old, self.new, fact("schedule-fact", "schedule"),
                      fact("result-fact", "result"), fact("report-fact", "report")]
        self.edges = [edge("schedule-edge", "old", "schedule-fact"),
                      dict(edge("result-edge", "schedule-fact", "result-fact"), relationship="calculated_from"),
                      dict(edge("report-edge", "result-fact", "report-fact"), relationship="describes")]
        self.artifacts = {"schedule": {"kind": "visit_schedule"},
                          "result": {"kind": "analysis_result"},
                          "report": {"kind": "report"}}

    def test_document_result_and_report_receive_distinct_actions(self):
        original = copy.deepcopy((self.changes, self.facts, self.edges, self.artifacts))
        findings = assess_impact(self.changes, self.facts, self.edges, artifact_lookup=self.artifacts)
        self.assertEqual({f["affected_fact_id"]: f["action"] for f in findings}, {
            "schedule-fact": "review_document", "result-fact": "rerun_analysis",
            "report-fact": "review_document",
        })
        self.assertTrue(all(f["status"] == "open" and f["resolution"] is None for f in findings))
        self.assertEqual((self.changes, self.facts, self.edges, self.artifacts), original)

    def test_known_document_relationships_request_review(self):
        for relationship in ("defines", "describes", "calculated_from", "requires", "covered_by"):
            for kind in ("document", "protocol", "analysis_plan", "visit_schedule", "report"):
                with self.subTest(relationship=relationship, kind=kind):
                    self.assertEqual(impact_action(relationship, {"kind": kind}), "review_document")

    def test_result_rules_require_both_relationship_and_kind(self):
        for relationship in ("defines", "calculated_from", "requires"):
            self.assertEqual(impact_action(relationship, "analysis_result"), "rerun_analysis")
        for relationship, artifact in (("describes", "analysis_result"), ("covered_by", "analysis_result"),
                                       ("unknown", "analysis_result"), (None, "analysis_result"),
                                       ("calculated_from", "unknown"), ("calculated_from", None),
                                       ("calculated_from", {}), ("calculated_from", {"kind": []})):
            with self.subTest(relationship=relationship, artifact=artifact):
                self.assertEqual(impact_action(relationship, artifact), "review_document")

    def test_unsupported_link_still_traverses_with_review_fallback(self):
        edges = [dict(self.edges[0], relationship="unrecognized")] + self.edges[1:]
        findings = assess_impact(self.changes, self.facts, edges, artifact_lookup=self.artifacts)
        self.assertEqual(len(findings), 3)
        self.assertEqual(next(f for f in findings if f["affected_fact_id"] == "schedule-fact")["action"], "review_document")

    def test_optional_lookup_preserves_findings_ids_paths_and_order(self):
        baseline = assess_impact(self.changes, self.facts, self.edges)
        enriched = assess_impact(self.changes, self.facts, self.edges, artifact_lookup=self.artifacts)
        for old, new in zip(baseline, enriched):
            self.assertEqual({k: v for k, v in old.items() if k != "action"},
                             {k: v for k, v in new.items() if k != "action"})
        self.assertTrue(all(f["action"] == "review_document" for f in baseline))
        self.assertEqual(assess_impact(self.changes, self.facts, reversed(self.edges),
                                      artifact_lookup=self.artifacts), enriched)

    def test_missing_artifact_entry_falls_back_without_losing_findings(self):
        findings = assess_impact(self.changes, self.facts, self.edges, artifact_lookup={})
        self.assertEqual(len(findings), 3)
        self.assertTrue(all(f["action"] == "review_document" for f in findings))

    def test_added_analysis_result_remains_link_review(self):
        added = compare_facts([], [fact("added", "result")])
        finding, = assess_impact(added, [fact("added", "result")], [], artifact_lookup=self.artifacts)
        self.assertEqual(finding["action"], "review_document")
        self.assertEqual(finding["path_edge_ids"], [])

    def test_pinned_or_proposed_results_never_request_reanalysis(self):
        for field, value in (("tracking", "pinned"), ("status", "proposed")):
            edges = [self.edges[0], dict(self.edges[1], **{field: value}), self.edges[2]]
            findings = assess_impact(self.changes, self.facts, edges, artifact_lookup=self.artifacts)
            self.assertEqual([f["affected_fact_id"] for f in findings], ["schedule-fact"])

    def test_alternate_computational_path_wins_and_supports_action(self):
        edges = self.edges + [dict(edge("a-direct", "old", "result-fact"), relationship="describes")]
        result = assess_impact(self.changes, self.facts, edges, artifact_lookup=self.artifacts)
        finding = next(f for f in result if f["affected_fact_id"] == "result-fact")
        self.assertEqual(finding["action"], "rerun_analysis")
        self.assertEqual(finding["path_edge_ids"], ["schedule-edge", "result-edge"])
        self.assertEqual(assess_impact(self.changes, self.facts, reversed(edges), artifact_lookup=self.artifacts), result)
        self.assertEqual(len(result), 3)

    def test_parallel_relationships_do_not_suppress_reanalysis(self):
        edges = [dict(edge("a-review", "old", "result-fact"), relationship="describes"),
                 dict(edge("z-rerun", "old", "result-fact"), relationship="calculated_from")]
        result, = assess_impact(self.changes, self.facts, edges, artifact_lookup=self.artifacts)
        self.assertEqual((result["action"], result["path_edge_ids"]), ("rerun_analysis", ["z-rerun"]))

    def test_repeated_amendments_have_distinct_findings_and_stable_retries(self):
        old2, new2 = dict(self.old, id="old2", version_id="v3"), dict(self.new, id="new2", version_id="v4")
        first = compare_facts([dict(self.old, version_id="v1")], [dict(self.new, version_id="v2")])
        second = compare_facts([old2], [new2])
        retry = compare_facts([dict(old2, id="retry-old")], [dict(new2, id="retry-new")])
        self.assertNotEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(second[0]["id"], retry[0]["id"])
        facts = self.facts + [old2, new2]
        edges = self.edges + [edge("second", "old2", "schedule-fact")]
        result = assess_impact(first + second, facts, edges, artifact_lookup=self.artifacts)
        self.assertEqual(len(result), 6)
        self.assertEqual(len({f["id"] for f in result}), 6)
        self.assertTrue(all(f["status"] == "open" for f in result))


if __name__ == "__main__":
    unittest.main()
