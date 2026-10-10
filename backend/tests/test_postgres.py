"""Run only against an empty, disposable database named trialsync_test*."""

import os
from pathlib import Path
import unittest
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
from fastapi.testclient import TestClient

from app.main import create_app
from app.persistence.memory import InMemoryRepository
from app.persistence.postgres import PostgresRepository
from app.persistence.seed import DEMO_STUDY_ID, seed_demo

TEST_URL = os.environ.get("TRIALSYNC_TEST_DATABASE_URL")


class PostgresFailureTest(unittest.TestCase):
    def test_connection_error_is_sanitized(self):
        repository = PostgresRepository("invalid database configuration")
        with TestClient(create_app(repository)) as client:
            response = client.get("/api/studies")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": {"code": "repository_unavailable",
            "message": "Database reads are temporarily unavailable"}})


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [normalized(item) for item in value]
        if items and all(isinstance(item, dict) and "id" in item for item in items):
            items.sort(key=lambda item: str(item["id"]))
        return items
    return value


@unittest.skipUnless(TEST_URL, "Set TRIALSYNC_TEST_DATABASE_URL to an empty disposable database")
class PostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(TEST_URL) as connection:
            name = connection.execute("SELECT current_database()").fetchone()[0]
            if not name.startswith("trialsync_test"):
                raise RuntimeError("Database integration tests require a trialsync_test* database")
            if connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError("Tests require an empty database; existing data is never reset")
            # Simulate Supabase's roles/default grants; the migration must revoke them.
            connection.execute("""DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated; END IF;
                END $$""")
            connection.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
            migrations = list((Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql"))
            if len(migrations) != 1:
                raise RuntimeError("Expected one baseline migration")
            connection.execute(migrations[0].read_text())
        seed_demo(TEST_URL)

    def setUp(self):
        self.repository = PostgresRepository(TEST_URL)
        self.client = TestClient(create_app(self.repository))

    def test_api_parity_with_memory_and_fresh_adapter(self):
        fixture_client = TestClient(create_app(InMemoryRepository()))
        paths = ["/api/studies"] + [f"/api/studies/{DEMO_STUDY_ID}/{suffix}"
                for suffix in ("artifacts", "graph", "findings", "audit")]
        for path in paths:
            actual = self.client.get(path)
            self.assertEqual(actual.status_code, 200)
            self.assertEqual(normalized(actual.json()), normalized(fixture_client.get(path).json()))
        self.assertEqual(len(PostgresRepository(TEST_URL).get_graph(DEMO_STUDY_ID).facts), 5)
        self.assertEqual(self.client.get(f"/api/studies/{uuid4()}/graph").status_code, 404)

    def test_seed_is_idempotent_and_preserves_reviews(self):
        def counts():
            with psycopg.connect(TEST_URL) as connection:
                return connection.execute("""SELECT
                    (SELECT count(*) FROM studies), (SELECT count(*) FROM memberships),
                    (SELECT count(*) FROM artifacts), (SELECT count(*) FROM artifact_versions),
                    (SELECT count(*) FROM source_fragments), (SELECT count(*) FROM facts),
                    (SELECT count(*) FROM dependencies), (SELECT count(*) FROM changes),
                    (SELECT count(*) FROM findings), (SELECT count(*) FROM audit_events),
                    (SELECT count(*) FROM jobs)""").fetchone()
        before = counts()
        finding = self.repository.list_findings(DEMO_STUDY_ID)[0]
        resolution = {"decision": "no_change", "note": "Reviewed synthetic evidence", "replacement_version_id": None}
        try:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("UPDATE findings SET status = 'resolved', resolution = %s WHERE id = %s",
                                   (Jsonb(resolution), finding.id))
            seed_demo(TEST_URL)
            seed_demo(TEST_URL)
            self.assertEqual(counts(), before)
            reviewed = next(row for row in self.repository.list_findings(DEMO_STUDY_ID) if row.id == finding.id)
            self.assertEqual(reviewed.status, "resolved")
            self.assertEqual(reviewed.resolution.note, resolution["note"])
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("UPDATE findings SET status = 'open', resolution = NULL WHERE id = %s", (finding.id,))

    def test_study_isolation_and_cross_study_edges_rejected(self):
        other_study = uuid4()
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("INSERT INTO studies(id, name) VALUES (%s, 'Another study')", (other_study,))
        try:
            self.assertEqual(self.repository.get_graph(other_study).facts, [])
            self.assertEqual(self.repository.list_findings(other_study), [])
            self.assertEqual(self.repository.list_artifacts(other_study), [])
            self.assertEqual(self.repository.list_audit(other_study), [])
            edge = self.repository.get_graph(DEMO_STUDY_ID).dependencies[0]
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with psycopg.connect(TEST_URL) as connection:
                    connection.execute("""INSERT INTO dependencies
                        (id, study_id, from_fact_id, to_fact_id, relationship, tracking, status, evidence)
                        VALUES (%s, %s, %s, %s, 'defines', 'current', 'confirmed', '[]')""",
                        (uuid4(), other_study, edge.from_fact_id, edge.to_fact_id))
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("DELETE FROM studies WHERE id = %s", (other_study,))

    def test_nullable_added_and_removed_changes(self):
        fact = self.repository.get_graph(DEMO_STUDY_ID).facts[0]
        for kind, before_id, after_id in (("added", None, fact.id), ("removed", fact.id, None)):
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("""INSERT INTO changes
                    (id, study_id, artifact_id, logical_key, before_fact_id, after_fact_id, before_value, after_value, kind)
                    VALUES (%s, %s, %s, %s, %s, %s, 'null', 'null', %s)""",
                    (uuid4(), DEMO_STUDY_ID, fact.artifact_id, fact.logical_key, before_id, after_id, kind))
                connection.rollback()
        with self.assertRaises(psycopg.errors.CheckViolation):
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("""INSERT INTO changes
                    (id, study_id, artifact_id, logical_key, before_fact_id, after_fact_id, before_value, after_value, kind)
                    VALUES (%s, %s, %s, 'invalid', NULL, NULL, 'null', 'null', 'modified')""",
                    (uuid4(), DEMO_STUDY_ID, fact.artifact_id))

    def test_rls_and_browser_grants_are_closed(self):
        with psycopg.connect(TEST_URL) as connection:
            rows = connection.execute("""SELECT c.relname, c.relrowsecurity,
                has_table_privilege('anon', c.oid, 'SELECT'),
                has_table_privilege('authenticated', c.oid, 'SELECT')
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'""").fetchall()
            self.assertEqual(len(rows), 11)
            for name, enabled, anon_read, member_read in rows:
                self.assertTrue(enabled, name)
                self.assertFalse(anon_read, name)
                self.assertFalse(member_read, name)

    def test_job_uniqueness_guard(self):
        version = self.repository.list_artifacts(DEMO_STUDY_ID)[0].versions[0]
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with psycopg.connect(TEST_URL) as connection:
                for _ in range(2):
                    connection.execute("INSERT INTO jobs (id, study_id, version_id, status) VALUES (%s, %s, %s, 'queued')",
                                       (uuid4(), DEMO_STUDY_ID, version.id))
