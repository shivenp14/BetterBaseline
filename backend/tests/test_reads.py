import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.models import Artifact, AuditEvent, Finding, Graph, Items, Study
from trialsync_test_support import demo_app as create_app
from app.persistence.memory import InMemoryRepository


class ReadAPITest(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepository()
        self.client = TestClient(create_app(self.repository))
        self.study_id = self.repository.list_studies()[0].id

    def test_all_reads_and_cross_record_references(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.get("/api/studies")
        self.assertEqual(response.status_code, 200)
        Items[Study].model_validate(response.json())
        results = {}
        for endpoint, model in (("artifacts", Items[Artifact]), ("graph", Graph),
                                ("findings", Items[Finding]), ("audit", Items[AuditEvent])):
            response = self.client.get(f"/api/studies/{self.study_id}/{endpoint}")
            self.assertEqual(response.status_code, 200)
            results[endpoint] = model.model_validate(response.json())
        graph = results["graph"]
        facts = {fact.id: fact for fact in graph.facts}
        artifacts = {artifact.id: artifact for artifact in results["artifacts"].items}
        versions = {version.id for artifact in artifacts.values() for version in artifact.versions}
        for fact in facts.values():
            self.assertIn(fact.artifact_id, artifacts)
            self.assertIn(fact.version_id, versions)
        edges = {edge.id: edge for edge in graph.dependencies}
        for edge in edges.values():
            self.assertIn(edge.from_fact_id, facts)
            self.assertIn(edge.to_fact_id, facts)
        pinned = [edge for edge in edges.values() if edge.tracking == "pinned"]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(facts[pinned[0].from_fact_id].value, 24)
        self.assertEqual(facts[pinned[0].to_fact_id].value, 24)
        self.assertEqual(len(results["findings"].items), 2)
        for finding in results["findings"].items:
            self.assertNotEqual(finding.affected_fact_id, pinned[0].to_fact_id)
            self.assertEqual(finding.affected_artifact_id, facts[finding.affected_fact_id].artifact_id)
            self.assertTrue(all(edge in edges for edge in finding.path_edge_ids))
            self.assertIsNone(finding.resolution)

    def test_unknown_and_malformed_studies_use_contract_errors(self):
        for endpoint in ("artifacts", "graph", "findings", "audit"):
            for study_id, status, code in ((uuid4(), 404, "study_not_found"),
                                           ("invalid", 422, "invalid_request")):
                response = self.client.get(f"/api/studies/{study_id}/{endpoint}")
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)
        self.assertEqual(self.client.get("/missing").json()["error"]["code"], "http_error")
        self.assertEqual(self.client.post("/api/studies").status_code, 405)

    def test_read_results_are_isolated(self):
        graph = self.repository.get_graph(self.study_id)
        graph.facts[0].value = 999
        graph.dependencies.clear()
        self.assertEqual(self.repository.get_graph(self.study_id).facts[0].value, 24)
        self.assertEqual(len(self.repository.get_graph(self.study_id).dependencies), 3)

    def test_repository_can_be_replaced(self):
        with TestClient(create_app(InMemoryRepository([]))) as client:
            self.assertEqual(client.get("/api/studies").json(), {"items": []})

    def test_local_ui_cors(self):
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            response = self.client.get("/api/studies", headers={"Origin": origin})
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
        response = self.client.get("/api/studies", headers={"Origin": "https://example.com"})
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
