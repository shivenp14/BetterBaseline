"""Worker safety checks against an empty disposable trialsync_test* database."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import psycopg

from app.main import create_app
from app.persistence.postgres import PostgresRepository
from app.persistence.repository import RepositoryUnavailable
from app.persistence.seed import DEMO_STUDY_ID, seed_demo
from app.persistence.storage import LocalPrivateStorage, StorageUnavailable, SupabasePrivateStorage
from app.persistence.worker import LeaseLost, PostgresWorkerStore, Results
from app.worker import DemoPipeline, Worker

TEST_URL = os.environ.get('TRIALSYNC_WORKER_TEST_DATABASE_URL')


class WorkerStorageTest(unittest.TestCase):
    def test_authenticated_supabase_read_is_bounded(self):
        requests = []
        def respond(request):
            requests.append(request)
            if '/bucket/' in str(request.url):
                return httpx.Response(200, json={'public': False})
            return httpx.Response(200, content=b'private source')
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            storage = SupabasePrivateStorage('https://example.supabase.co', 'test-only-key', 'private', client)
            self.assertEqual(storage.read('study/source'), b'private source')
            self.assertTrue(str(requests[-1].url).endswith('/object/authenticated/private/study/source'))
            self.assertEqual(requests[-1].headers['Authorization'], 'Bearer test-only-key')
            with self.assertRaises(StorageUnavailable):
                storage.read('study/source', max_bytes=2)

    def test_local_read_limit(self):
        with TemporaryDirectory() as directory:
            storage = LocalPrivateStorage(Path(directory))
            storage.put('source', b'123', 'text/plain')
            self.assertEqual(storage.read('source', 3), b'123')
            with self.assertRaises(StorageUnavailable):
                storage.read('source', 2)


@unittest.skipUnless(TEST_URL, 'Set TRIALSYNC_WORKER_TEST_DATABASE_URL to an empty disposable database')
class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(TEST_URL) as connection:
            if not connection.execute('SELECT current_database()').fetchone()[0].startswith('trialsync_test'):
                raise RuntimeError('Worker tests require a disposable trialsync_test* database')
            if connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError('Existing database is never reset')
            for path in sorted((Path(__file__).resolve().parents[2] / 'supabase/migrations').glob('*.sql')):
                connection.execute(path.read_text())
        seed_demo(TEST_URL)

    def setUp(self):
        # Isolate pending test jobs inside our verified, disposable database.
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("UPDATE jobs SET status='failed' WHERE status IN ('queued','running')")
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = LocalPrivateStorage(Path(self.directory.name))
        self.reads = PostgresRepository(TEST_URL)
        self.store = PostgresWorkerStore(TEST_URL, retry_seconds=0)
        self.pipeline = DemoPipeline()
        self.worker = Worker(self.store, self.storage, self.pipeline)

    def upload(self, content=None):
        artifact = next(a for a in self.reads.list_artifacts(DEMO_STUDY_ID) if a.kind == 'protocol')
        baseline = next(f for f in self.reads.get_graph(DEMO_STUDY_ID).facts
                        if f.artifact_id == artifact.id and f.version_id == artifact.versions[0].id)
        if content is None:
            content = json.dumps({'facts': [{'logical_key': baseline.logical_key, 'label': baseline.label,
                'value': 36, 'unit': baseline.unit, 'locator': 'fixture:1', 'quote': 'Endpoint week 36'}]}).encode()
        with TestClient(create_app(self.reads, storage=self.storage)) as client:
            response = client.post(f'/api/artifacts/{artifact.id}/versions',
                files={'file': ('revision.json', content, 'application/json')})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def results(self, claim):
        context = self.store.context(claim)
        content = self.storage.read(context.version.storage_path)
        facts = self.pipeline.extract(content, context)
        changes = self.pipeline.compare(facts, context)
        return context, Results(facts, changes, self.pipeline.assess(changes, facts, context))

    def counts(self, version_id):
        with psycopg.connect(TEST_URL) as connection:
            return connection.execute('''SELECT
                (SELECT count(*) FROM facts WHERE version_id=%s),
                (SELECT count(*) FROM changes c JOIN facts f ON c.after_fact_id=f.id WHERE f.version_id=%s),
                (SELECT count(*) FROM findings n JOIN changes c ON n.change_id=c.id
                    JOIN facts f ON c.after_fact_id=f.id WHERE f.version_id=%s)''',
                (version_id, version_id, version_id)).fetchone()

    def expire(self, claim):
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("UPDATE jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (claim.job_id,))

    def test_upload_to_findings_once_preserves_approved_graph(self):
        upload = self.upload()
        before = self.store.context(self.store.claim())  # Reclaim after simulating a crashed process.
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("UPDATE jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s", (upload['job']['id'],))
        self.assertTrue(self.worker.run_once())
        self.assertFalse(self.worker.run_once())
        with TestClient(create_app(self.reads, storage=self.storage)) as client:
            polled = client.get(f"/api/jobs/{upload['job']['id']}").json()
            findings = client.get(f'/api/studies/{DEMO_STUDY_ID}/findings').json()['items']
        self.assertEqual(polled['status'], 'succeeded')
        self.assertEqual(self.reads.get_version(upload['version']['id']).version.status, 'ready')
        self.assertEqual(self.counts(upload['version']['id']), (1, 1, 2))
        new_ids = {f.id for f in self.reads.get_graph(DEMO_STUDY_ID).facts if str(f.version_id) == upload['version']['id']}
        change_id = str(self.pipeline.compare([f for f in self.reads.get_graph(DEMO_STUDY_ID).facts if f.id in new_ids], before)[0].id)
        added = [f for f in findings if f['change_id'] == change_id]
        self.assertEqual(len(added), 2)
        self.assertTrue(all(f['sources'] and f['explanation'] for f in added))
        after_claim_context = before.approved_versions
        with psycopg.connect(TEST_URL) as connection:
            approved = dict(connection.execute('SELECT id, approved_version_id FROM artifacts').fetchall())
        self.assertEqual(approved, after_claim_context)
        self.assertTrue(all(f['affected_artifact_id'] != str(a.id) for f in added
                            for a in self.reads.list_artifacts(DEMO_STUDY_ID) if a.kind == 'report'))

    def test_concurrent_claim_is_exclusive(self):
        upload = self.upload()
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: self.store.claim(), range(4)))
        self.assertEqual(sum(c is not None for c in claims), 1)
        claim = next(c for c in claims if c)
        self.assertEqual(str(claim.job_id), upload['job']['id'])
        context, results = self.results(claim)
        self.store.complete(claim, context, results)
        with self.assertRaises(LeaseLost):
            self.store.complete(claim, context, results)
        self.assertEqual(self.counts(claim.version_id), (1, 1, 2))

    def test_expired_lease_fences_old_attempt(self):
        self.upload()
        old = self.store.claim()
        context, results = self.results(old)
        self.expire(old)
        new = self.store.claim()
        self.assertEqual(new.attempt, 2)
        self.assertNotEqual(old.token, new.token)
        for action in (lambda: self.store.complete(old, context, results),
                       lambda: self.store.fail(old, 'stale'), lambda: self.store.heartbeat(old, 'stale')):
            with self.assertRaises(LeaseLost):
                action()
        self.store.complete(new, *self.results(new))
        self.assertEqual(self.counts(new.version_id), (1, 1, 2))

    def test_expired_final_attempt_becomes_failed(self):
        upload = self.upload()
        store = PostgresWorkerStore(TEST_URL, max_attempts=1)
        claim = store.claim()
        self.expire(claim)
        self.assertIsNone(store.claim())
        self.assertEqual(self.reads.get_job(claim.job_id).job.status, 'failed')
        self.assertIn('lease_expired', self.reads.get_job(claim.job_id).job.error)
        self.assertEqual(self.reads.get_version(upload['version']['id']).version.status, 'failed')
        self.assertEqual(self.counts(claim.version_id), (0, 0, 0))

    def test_invalid_source_retries_bounded_and_reports_error(self):
        upload = self.upload(b'not a JSON fixture')
        for _ in range(3):
            self.assertTrue(self.worker.run_once())
        self.assertFalse(self.worker.run_once())
        job = self.reads.get_job(upload['job']['id']).job
        self.assertEqual(job.status, 'failed')
        self.assertEqual(job.error, 'extracting: invalid_demo_json')
        self.assertEqual(self.counts(upload['version']['id']), (0, 0, 0))

    def test_hash_mismatch_does_not_invoke_adapter(self):
        upload = self.upload()
        version = self.reads.get_version(upload['version']['id'])
        self.storage._path(version.storage_path).write_bytes(b'changed')
        self.worker.run_once()
        self.assertEqual(self.reads.get_job(upload['job']['id']).job.error, 'loading: source_hash_mismatch')
        self.assertEqual(self.counts(upload['version']['id']), (0, 0, 0))

    def test_retry_schedule_is_respected(self):
        self.upload()
        store = PostgresWorkerStore(TEST_URL, retry_seconds=3600)
        claim = store.claim()
        store.fail(claim, 'test failure')
        self.assertIsNone(store.claim())
        self.assertEqual(self.reads.get_job(claim.job_id).job.stage, 'retry_wait')

    def test_transaction_rolls_back_partial_results_then_succeeds(self):
        self.upload()
        claim = self.store.claim()
        context, results = self.results(claim)
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("""CREATE FUNCTION reject_worker_findings() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'test rejection'; END $$;
                CREATE TRIGGER reject_worker_findings BEFORE INSERT ON findings
                FOR EACH ROW EXECUTE FUNCTION reject_worker_findings()""")
        try:
            with self.assertRaises(RepositoryUnavailable):
                self.store.complete(claim, context, results)
            self.assertEqual(self.counts(claim.version_id), (0, 0, 0))
            self.assertEqual(self.reads.get_job(claim.job_id).job.status, 'running')
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute('DROP TRIGGER reject_worker_findings ON findings; DROP FUNCTION reject_worker_findings()')
        self.store.complete(claim, context, results)
        self.assertEqual(self.counts(claim.version_id), (1, 1, 2))

    def test_scope_and_approval_changes_rejected(self):
        self.upload()
        claim = self.store.claim()
        context, results = self.results(claim)
        results.facts[0].version_id = uuid4()
        with self.assertRaises(ValueError):
            self.store.complete(claim, context, results)
        context, results = self.results(claim)
        artifact_id = context.version.version.artifact_id
        old = context.approved_versions[artifact_id]
        with psycopg.connect(TEST_URL) as connection:
            connection.execute('UPDATE artifacts SET approved_version_id=NULL WHERE id=%s', (artifact_id,))
        try:
            with self.assertRaises(ValueError):
                self.store.complete(claim, context, results)
            self.assertEqual(self.counts(claim.version_id), (0, 0, 0))
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute('UPDATE artifacts SET approved_version_id=%s WHERE id=%s', (old, artifact_id))

    def test_removed_snapshot_is_persisted_with_nullable_after(self):
        upload = self.upload(b'{"facts": []}')
        claim = self.store.claim()
        context, results = self.results(claim)
        change_id = results.changes[0].id
        self.expire(claim)
        self.worker.run_once()
        with psycopg.connect(TEST_URL) as connection:
            row = connection.execute("SELECT kind, after_fact_id FROM changes WHERE id=%s",
                                     (change_id,)).fetchone()
        self.assertEqual(row, ('removed', None))
        self.assertEqual(self.reads.get_job(upload['job']['id']).job.status, 'succeeded')
        # A separate candidate can remove the same approved snapshot independently.
        second = self.upload(b'{"facts": []}')
        self.worker.run_once()
        self.assertEqual(self.reads.get_job(second['job']['id']).job.status, 'succeeded')
        with psycopg.connect(TEST_URL) as connection:
            removed = connection.execute("SELECT count(*) FROM changes WHERE kind='removed' AND candidate_version_id IN (%s,%s)",
                (upload['version']['id'], second['version']['id'])).fetchone()[0]
        self.assertEqual(removed, 2)

    def test_graph_review_change_rejects_stale_impact(self):
        self.upload()
        claim = self.store.claim()
        context, results = self.results(claim)
        edge = next(e for e in context.graph.dependencies if e.status == 'confirmed' and e.tracking == 'current')
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("UPDATE dependencies SET tracking='pinned' WHERE id=%s", (edge.id,))
        try:
            with self.assertRaises(ValueError):
                self.store.complete(claim, context, results)
            self.assertEqual(self.counts(claim.version_id), (0, 0, 0))
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute("UPDATE dependencies SET tracking='current' WHERE id=%s", (edge.id,))

    def test_new_fact_persists_added_change_and_link_review(self):
        upload = self.upload(json.dumps({'facts': [{'logical_key': 'new_demo_endpoint', 'label': 'New endpoint',
            'value': 36, 'unit': 'week', 'locator': 'fixture:1', 'quote': 'New endpoint week 36'}]}).encode())
        self.worker.run_once()
        with psycopg.connect(TEST_URL) as connection:
            row = connection.execute('''SELECT c.kind, c.before_fact_id, n.path_edge_ids
                FROM changes c JOIN facts f ON c.after_fact_id=f.id JOIN findings n ON c.id=n.change_id
                WHERE f.version_id=%s''', (upload['version']['id'],)).fetchone()
        self.assertEqual(row, ('added', None, []))
        self.assertEqual(self.reads.get_job(upload['job']['id']).job.status, 'succeeded')

    def test_adapter_error_does_not_expose_document_or_credentials(self):
        upload = self.upload()
        class BrokenAdapter(DemoPipeline):
            def extract(self, content, context):
                raise RuntimeError('credential and private document content')
        Worker(self.store, self.storage, BrokenAdapter()).run_once()
        self.assertEqual(self.reads.get_job(upload['job']['id']).job.error, 'extracting: processing_error')
        self.assertEqual(self.counts(upload['version']['id']), (0, 0, 0))

    def test_expiration_during_result_writes_rolls_back(self):
        self.upload()
        claim = self.store.claim()
        context, results = self.results(claim)
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("""CREATE FUNCTION expire_worker_during_write() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN UPDATE jobs SET lease_expires_at=clock_timestamp()-interval '1 second'
                WHERE version_id=NEW.version_id; RETURN NEW; END $$;
                CREATE TRIGGER expire_worker_during_write AFTER INSERT ON facts
                FOR EACH ROW EXECUTE FUNCTION expire_worker_during_write()""")
        try:
            with self.assertRaises(LeaseLost):
                self.store.complete(claim, context, results)
            self.assertEqual(self.counts(claim.version_id), (0, 0, 0))
            self.assertEqual(self.reads.get_job(claim.job_id).job.status, 'running')
        finally:
            with psycopg.connect(TEST_URL) as connection:
                connection.execute('DROP TRIGGER expire_worker_during_write ON facts; DROP FUNCTION expire_worker_during_write()')
