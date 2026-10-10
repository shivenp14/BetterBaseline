"""Fixture coverage for task #30 and its comparison integration."""

import copy
import unittest
from uuid import UUID

from app.domain import assess_impact, compare_facts


def fact(identifier, artifact=None, value=24):
    return dict(id=identifier, artifact_id=artifact or identifier,
                version_id="v1", logical_key="endpoint.week", label="Endpoint",
                value=value, unit="week", source={})


def edge(identifier, upstream, dependent, tracking="current", status="confirmed"):
    return dict(id=identifier, from_fact_id=upstream, to_fact_id=dependent,
                tracking=tracking, status=status, relationship="defines", evidence=[])


class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.before = fact("protocol-v1", "protocol")
        self.after = fact("protocol-v2", "protocol", 36)
        self.changes = compare_facts([self.before], [self.after])
        self.facts = [self.before, self.after, fact("schedule"), fact("analysis"), fact("report")]
        self.edges = [edge("schedule-edge", "protocol-v1", "schedule"),
                      edge("analysis-edge", "schedule", "analysis"),
                      edge("report-edge", "analysis", "report", tracking="pinned")]

    def test_amendment_reaches_schedule_and_analysis_but_not_pinned_report(self):
        original = copy.deepcopy((self.changes, self.facts, self.edges))
        findings = assess_impact(self.changes, self.facts, self.edges, study_id="study")
        by_fact = {f["affected_fact_id"]: f for f in findings}
        self.assertEqual(set(by_fact), {"schedule", "analysis"})
        self.assertEqual(by_fact["schedule"]["path_edge_ids"], ["schedule-edge"])
        self.assertEqual(by_fact["analysis"]["path_edge_ids"], ["schedule-edge", "analysis-edge"])
        for finding in findings:
            self.assertEqual(finding["study_id"], "study")
            self.assertEqual(finding["status"], "open")
            self.assertEqual(finding["affected_artifact_id"], finding["affected_fact_id"])
            self.assertEqual(UUID(finding["id"]).version, 5)
            self.assertIsNone(finding["resolution"])
        self.assertEqual((self.changes, self.facts, self.edges), original)

    def test_cycles_self_loops_diamonds_and_duplicate_records(self):
        edges = self.edges + [edge("back", "analysis", "protocol-v1"),
                              edge("self", "schedule", "schedule"),
                              edge("direct", "protocol-v1", "analysis")]
        expected = assess_impact(self.changes, self.facts, edges)
        self.assertEqual(len(expected), 2)
        self.assertEqual(expected[0]["path_edge_ids"], ["direct"])
        self.assertEqual(assess_impact(self.changes * 2, self.facts * 2, edges * 2), expected)
        self.assertEqual(assess_impact(reversed(self.changes), reversed(self.facts), reversed(edges)), expected)

    def test_equal_length_paths_have_stable_tie_break(self):
        facts = [fact(x) for x in ("root", "left", "right", "sink")]
        change = dict(self.changes[0], before_fact_id="root")
        edges = [edge("b", "root", "right"), edge("a", "root", "left"),
                 edge("c", "left", "sink"), edge("d", "right", "sink")]
        result = assess_impact([change], facts, edges)
        sink = next(f for f in result if f["affected_fact_id"] == "sink")
        self.assertEqual(sink["path_edge_ids"], ["a", "c"])
        self.assertEqual(assess_impact([change], facts, reversed(edges)), result)

    def test_only_confirmed_current_edges_and_forward_direction(self):
        edges = [edge("proposed", "protocol-v1", "schedule", status="proposed"),
                 edge("pinned", "protocol-v1", "analysis", tracking="pinned"),
                 edge("incoming", "report", "protocol-v1"),
                 edge("new-snapshot", "protocol-v2", "analysis")]
        self.assertEqual(assess_impact(self.changes, self.facts, edges), [])

    def test_pinned_branch_does_not_reach_current_descendants(self):
        edges = [edge("pinned", "protocol-v1", "schedule", tracking="pinned"),
                 edge("current", "schedule", "analysis")]
        self.assertEqual(assess_impact(self.changes, self.facts, edges), [])

    def test_removed_fact_uses_old_graph(self):
        removed = compare_facts([self.before], [])
        self.assertEqual(len(assess_impact(removed, self.facts, self.edges)), 2)

    def test_added_fact_requires_link_review_without_propagation(self):
        added = compare_facts([], [self.after])
        result = assess_impact(added, self.facts, [edge("candidate", "protocol-v2", "analysis")])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["affected_fact_id"], "protocol-v2")
        self.assertEqual(result[0]["path_edge_ids"], [])
        self.assertEqual(result[0]["action"], "review_document")

    def test_distinct_changes_get_distinct_findings_for_same_dependent(self):
        changes = self.changes + [dict(self.changes[0], id="second-change")]
        result = assess_impact(changes, self.facts, self.edges)
        self.assertEqual(len(result), 4)
        self.assertEqual(len({f["id"] for f in result}), 4)
        self.assertEqual(assess_impact(reversed(changes), self.facts, self.edges), result)

    def test_invalid_graph_and_missing_old_snapshots_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "missing endpoint"):
            assess_impact(self.changes, self.facts, [edge("broken", "protocol-v1", "unknown")])
        with self.assertRaisesRegex(ValueError, "before fact"):
            assess_impact(self.changes, self.facts[1:], [])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            assess_impact(self.changes, self.facts, self.edges + [dict(self.edges[0], to_fact_id="report")])
        with self.assertRaisesRegex(ValueError, "after fact"):
            assess_impact(compare_facts([], [self.after]), [self.before], [])

    def test_empty_and_unlinked_changes(self):
        self.assertEqual(assess_impact([], [], []), [])
        self.assertEqual(assess_impact(self.changes, self.facts, []), [])


if __name__ == "__main__":
    unittest.main()
