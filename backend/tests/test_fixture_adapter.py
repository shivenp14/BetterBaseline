import sys
import unittest
from pathlib import Path
from uuid import UUID

# Ensure backend directory is in sys.path for test runners from any working directory
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.ingestion.fixture_adapter import (
    extract_version_fixture,
    get_baseline_graph,
    get_fixtures_dir,
    get_revision_delta,
    get_sources_dir,
    load_demo_fixtures,
    load_source_text,
    verify_evidence_integrity,
)


class TestFixtureAdapter(unittest.TestCase):
    """Verify demo source text files, fixtures schema, and extraction adapter."""

    def test_sources_exist_and_readable(self):
        """All five synthetic source documents must exist and have non-trivial content."""
        expected_files = [
            "protocol-v1.txt",
            "protocol-v2.txt",
            "analysis-v1.txt",
            "schedule-v1.txt",
            "report-v1.txt",
        ]
        sources_dir = get_sources_dir()
        for filename in expected_files:
            file_path = sources_dir / filename
            self.assertTrue(file_path.is_file(), f"Missing demo source file: {filename}")
            content = load_source_text(filename)
            self.assertGreater(len(content.strip()), 100, f"File {filename} is too short")

    def test_evidence_integrity(self):
        """Every quote and locator cited in fixtures must exist verbatim in the source text."""
        results = verify_evidence_integrity()
        self.assertEqual(len(results), 5, "Expected exactly 5 facts across all demo versions")
        for res in results:
            self.assertTrue(
                res["quote_match"],
                f"Quote '{res['quote']}' not found in {res['filename']}",
            )
            self.assertTrue(
                res["locator_match"],
                f"Locator '{res['locator']}' not found in {res['filename']}",
            )
            self.assertTrue(res["valid"])

    def test_extract_version_fixture_protocol(self):
        """Protocol v1 and v2 extract expected facts with matching logical keys and amended values."""
        v1_facts = extract_version_fixture("protocol-v1.txt")
        self.assertEqual(len(v1_facts), 1)
        self.assertEqual(v1_facts[0]["logical_key"], "endpoint.week")
        self.assertEqual(v1_facts[0]["value"], 24)
        self.assertEqual(v1_facts[0]["unit"], "week")

        v2_facts = extract_version_fixture("protocol-v2.txt")
        self.assertEqual(len(v2_facts), 1)
        self.assertEqual(v2_facts[0]["logical_key"], "endpoint.week")
        self.assertEqual(v2_facts[0]["value"], 36)
        self.assertEqual(v2_facts[0]["unit"], "week")

        # They share the exact same logical key
        self.assertEqual(v1_facts[0]["logical_key"], v2_facts[0]["logical_key"])

    def test_extract_version_fixture_downstream(self):
        """Analysis plan, visit schedule, and historical report extract value 24 facts."""
        for filename in ["analysis-v1.txt", "schedule-v1.txt", "report-v1.txt"]:
            facts = extract_version_fixture(filename)
            self.assertEqual(len(facts), 1, f"Expected 1 fact for {filename}")
            self.assertEqual(facts[0]["logical_key"], "endpoint.week")
            self.assertEqual(facts[0]["value"], 24)

    def test_uuid_validity(self):
        """All entities in demo fixtures must use valid RFC 4122 UUID strings."""
        data = load_demo_fixtures()[0]
        # Study UUID
        UUID(data["study"]["id"])

        # Artifact & version UUIDs
        for art in data["artifacts"]:
            UUID(art["id"])
            UUID(art["study_id"])
            for v in art["versions"]:
                UUID(v["id"])
                UUID(v["artifact_id"])
                UUID(v["study_id"])
                if v["previous_version_id"]:
                    UUID(v["previous_version_id"])

        # Fact UUIDs
        for fact in data["graph"]["facts"]:
            UUID(fact["id"])
            UUID(fact["artifact_id"])
            UUID(fact["version_id"])
            UUID(fact["source"]["fragment_id"])

        # Dependency UUIDs
        for dep in data["graph"]["dependencies"]:
            UUID(dep["id"])
            UUID(dep["from_fact_id"])
            UUID(dep["to_fact_id"])
            for ev in dep["evidence"]:
                UUID(ev["fragment_id"])

        # Change UUIDs
        for change in data["changes"]:
            UUID(change["id"])
            UUID(change["artifact_id"])
            if change["before_fact_id"]:
                UUID(change["before_fact_id"])
            if change["after_fact_id"]:
                UUID(change["after_fact_id"])

        # Finding UUIDs
        for finding in data["findings"]:
            UUID(finding["id"])
            UUID(finding["study_id"])
            UUID(finding["change_id"])
            UUID(finding["affected_fact_id"])
            UUID(finding["affected_artifact_id"])
            for edge_id in finding["path_edge_ids"]:
                UUID(edge_id)

    def test_baseline_graph_and_pinned_edge(self):
        """Baseline graph must have 4 v1 facts, 3 dependencies, and 1 pinned dependency."""
        baseline = get_baseline_graph()
        self.assertEqual(len(baseline["graph"]["facts"]), 4)
        for f in baseline["graph"]["facts"]:
            self.assertEqual(f["value"], 24)

        dependencies = baseline["graph"]["dependencies"]
        self.assertEqual(len(dependencies), 3)

        pinned_deps = [d for d in dependencies if d.get("tracking") == "pinned"]
        self.assertEqual(len(pinned_deps), 1)
        self.assertEqual(pinned_deps[0]["relationship"], "defines")

    def test_revision_delta_and_findings(self):
        """Revision delta must contain the week 36 fact, the modified change, and 2 findings."""
        delta = get_revision_delta()
        self.assertEqual(len(delta["new_facts"]), 1)
        self.assertEqual(delta["new_facts"][0]["value"], 36)

        changes = delta["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["before_value"], 24)
        self.assertEqual(changes[0]["after_value"], 36)
        self.assertEqual(changes[0]["kind"], "modified")

        findings = delta["findings"]
        self.assertEqual(len(findings), 2)
        for finding in findings:
            self.assertEqual(finding["action"], "review_document")
            self.assertEqual(finding["status"], "open")


if __name__ == "__main__":
    unittest.main()
