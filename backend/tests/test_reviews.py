from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.types.json import Jsonb

from app.api.models import FindingReview
from app.api.review_policy import LocalReviewPolicy, ReviewConflict
from app.api.uploads import StudyAccessDenied
from app.main import create_app
from app.persistence.memory import InMemoryRepository
from app.persistence.postgres import PostgresRepository
from app.persistence.repository import RepositoryUnavailable
from app.persistence.seed import DEMO_ACTOR_ID, DEMO_STUDY_ID, seed_demo
from app.persistence.storage import LocalPrivateStorage
from app.persistence.worker import PostgresWorkerStore
from app.worker import DemoPipeline, Worker

TEST_URL = os.environ.get('TRIALSYNC_REVIEW_TEST_DATABASE_URL')


def resolution(decision='no_change', note='Reviewed synthetic evidence', replacement_version_id=None):
    return {'decision': decision, 'note': note, 'replacement_version_id': replacement_version_id}


class ReviewAPITest(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepository()
        self.finding = self.repository.list_findings(DEMO_STUDY_ID)[0]
        self.client = TestClient(create_app(self.repository))

    def test_justified_resolution_audit_and_idempotence(self):
        before = len(self.repository.list_audit(DEMO_STUDY_ID))
        path = f'/api/findings/{self.finding.id}'
        patch = {'status': 'resolved', 'owner_id': str(DEMO_ACTOR_ID), 'resolution': resolution()}
        result = self.client.patch(path, json=patch)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'resolved')
        audit = self.repository.list_audit(DEMO_STUDY_ID)
        self.assertEqual(len(audit), before+1)
        self.assertEqual(audit[-1].actor_id, DEMO_ACTOR_ID)
        self.assertEqual(audit[-1].entity_id, self.finding.id)
        self.assertEqual(audit[-1].action, 'finding.updated')
        self.assertEqual(self.client.patch(path, json=patch).status_code, 200)
        self.assertEqual(len(self.repository.list_audit(DEMO_STUDY_ID)), before+1)
        self.assertEqual(self.client.patch(path, json={'status': 'open', 'resolution': None}).status_code, 409)

    def test_invalid_resolutions_and_owner_do_not_mutate(self):
        patches = [{}, {'status': None}, {'status': 'resolved'},
                   {'status': 'resolved', 'resolution': resolution(note=' ')},
                   {'status': 'resolved', 'resolution': resolution('reanalysis_requested')},
                   {'status': 'resolved', 'resolution': resolution('updated')},
                   {'status': 'dismissed', 'resolution': resolution('updated', replacement_version_id=str(uuid4()))},
                   {'status': 'in_review', 'resolution': resolution()},
                   {'status': 'open', 'resolution': resolution('reanalysis_requested')},
                   {'owner_id': str(uuid4())}, {'actor_id': str(uuid4())}]
        before = self.repository.list_audit(DEMO_STUDY_ID)
        for patch in patches:
            with self.subTest(patch=patch):
                response = self.client.patch(f'/api/findings/{self.finding.id}', json=patch)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.repository.get_finding(self.finding.id), self.finding)
        self.assertEqual(self.repository.list_audit(DEMO_STUDY_ID), before)

    def test_reanalysis_stays_pending_and_clear_owner(self):
        path = f'/api/findings/{self.finding.id}'
        response = self.client.patch(path, json={'status': 'in_review', 'owner_id': str(DEMO_ACTOR_ID),
                                               'resolution': resolution('reanalysis_requested')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'in_review')
        self.assertEqual(self.client.patch(path, json={'status': 'resolved'}).status_code, 422)
        cleared = self.client.patch(path, json={'owner_id': None})
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()['owner_id'])

    def test_access_precedes_mutation_and_unknown_ids(self):
        class Deny:
            def require_study_access(self, study_id):
                raise StudyAccessDenied
        client = TestClient(create_app(self.repository, study_access=Deny()))
        before = self.repository.list_audit(DEMO_STUDY_ID)
        self.assertEqual(client.patch(f'/api/findings/{self.finding.id}', json={'status':'in_review'}).status_code, 403)
        edge = self.repository.get_graph(DEMO_STUDY_ID).dependencies[0]
        self.assertEqual(client.patch(f'/api/dependencies/{edge.id}', json={'status':'confirmed'}).status_code, 403)
        version = self.repository.list_artifacts(DEMO_STUDY_ID)[0].versions[0]
        self.assertEqual(client.post(f'/api/versions/{version.id}/approve').status_code, 403)
        self.assertEqual(self.repository.list_audit(DEMO_STUDY_ID), before)
        self.assertEqual(self.client.patch(f'/api/findings/{uuid4()}', json={'status':'in_review'}).status_code, 404)

    def test_memory_confirmation_projection_and_pinned_history(self):
        fixture = self.repository._get(DEMO_STUDY_ID)
        fixture.graph.dependencies[0].status = 'proposed'
        self.repository = InMemoryRepository([fixture])
        client = TestClient(create_app(self.repository))
        original = self.repository.get_graph(DEMO_STUDY_ID)
        edge = original.dependencies[0]
        confirmed = client.patch(f'/api/dependencies/{edge.id}', json={'status':'confirmed'})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        protocol = next(a for a in fixture.artifacts if a.kind == 'protocol')
        result = client.post(f'/api/versions/{protocol.versions[-1].id}/approve')
        self.assertEqual(result.status_code, 200, result.text)
        graph = self.repository.get_graph(DEMO_STUDY_ID)
        self.assertEqual(len(graph.dependencies), len(original.dependencies)+2)
        self.assertEqual(next(e for e in graph.dependencies if e.id == original.dependencies[-1].id), original.dependencies[-1])
        self.assertEqual(len(self.repository.list_findings(DEMO_STUDY_ID)), len(fixture.findings))
        audit_count = len(self.repository.list_audit(DEMO_STUDY_ID))
        self.assertEqual(client.post(f'/api/versions/{protocol.versions[-1].id}/approve').status_code, 200)
        self.assertEqual(len(self.repository.list_audit(DEMO_STUDY_ID)), audit_count)


@unittest.skipUnless(TEST_URL, 'Set TRIALSYNC_REVIEW_TEST_DATABASE_URL to an empty disposable database')
class PostgresReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(TEST_URL) as connection:
            if not connection.execute('SELECT current_database()').fetchone()[0].startswith('trialsync_test'):
                raise RuntimeError('Review tests require a disposable trialsync_test* database')
            if connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError('Existing data is never reset')
            for migration in sorted((Path(__file__).resolve().parents[2] / 'supabase/migrations').glob('*.sql')):
                connection.execute(migration.read_text())
        seed_demo(TEST_URL)

    def setUp(self):
        self.repository = PostgresRepository(TEST_URL)
        self.policy = LocalReviewPolicy()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = LocalPrivateStorage(Path(self.temp.name))
        self.client = TestClient(create_app(self.repository, storage=self.storage))
        # Each case uses its own study cloned from the synthetic fixture and new UUIDs.
        raw = self.repository_fixture()
        self.study_id = raw['study']['id']
        self.fixture = raw
        with psycopg.connect(TEST_URL) as connection:
            connection.execute('INSERT INTO studies (id,name) VALUES (%s,%s)', (self.study_id,'Review test study'))
            connection.execute("INSERT INTO memberships(study_id,user_id,role) VALUES (%s,%s,'owner')", (self.study_id,DEMO_ACTOR_ID))
            for a in raw['artifacts']:
                connection.execute('INSERT INTO artifacts(id,study_id,name,kind) VALUES (%s,%s,%s,%s)', (a['id'],self.study_id,a['name'],a['kind']))
                for v in a['versions']:
                    connection.execute('''INSERT INTO artifact_versions(id,study_id,artifact_id,version_number,previous_version_id,filename,status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)''', (v['id'],self.study_id,a['id'],v['version_number'],v['previous_version_id'],v['filename'],v['status']))
                connection.execute('UPDATE artifacts SET approved_version_id=%s WHERE id=%s', (a['versions'][0]['id'],a['id']))
            for f in raw['graph']['facts']:
                s=f['source']
                connection.execute('INSERT INTO source_fragments(id,study_id,artifact_id,version_id,locator,quote) VALUES (%s,%s,%s,%s,%s,%s)',
                    (s['fragment_id'],self.study_id,f['artifact_id'],f['version_id'],s['locator'],s['quote']))
                connection.execute('INSERT INTO facts(id,study_id,artifact_id,version_id,fragment_id,logical_key,label,value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (f['id'],self.study_id,f['artifact_id'],f['version_id'],s['fragment_id'],f['logical_key'],f['label'],Jsonb(f['value']),f['unit']))
            for e in raw['graph']['dependencies']:
                connection.execute('INSERT INTO dependencies(id,study_id,from_fact_id,to_fact_id,relationship,tracking,status,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (e['id'],self.study_id,e['from_fact_id'],e['to_fact_id'],e['relationship'],e['tracking'],e['status'],Jsonb(e['evidence'])))
            for c in raw['changes']:
                connection.execute('INSERT INTO changes(id,study_id,artifact_id,logical_key,before_fact_id,after_fact_id,before_value,after_value,kind) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (c['id'],self.study_id,c['artifact_id'],c['logical_key'],c['before_fact_id'],c['after_fact_id'],Jsonb(c['before_value']),Jsonb(c['after_value']),c['kind']))
            for f in raw['findings']:
                connection.execute('''INSERT INTO findings(id,study_id,change_id,affected_fact_id,affected_artifact_id,path_edge_ids,action,explanation,sources,status,owner_id,resolution)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (f['id'],self.study_id,f['change_id'],f['affected_fact_id'],f['affected_artifact_id'],f['path_edge_ids'],f['action'],f['explanation'],Jsonb(f['sources']),f['status'],None,None))
        self.finding_id = raw['findings'][0]['id']
        self.edge_id = raw['graph']['dependencies'][0]['id']

    @staticmethod
    def repository_fixture():
        from importlib.resources import files
        raw=json.loads(files('app.persistence').joinpath('fixtures.json').read_text())[0]
        ids={}
        def remap(value):
            if isinstance(value, dict): return {k:remap(v) for k,v in value.items()}
            if isinstance(value, list): return [remap(v) for v in value]
            if isinstance(value, str) and len(value)==36 and value.count('-')==4:
                return ids.setdefault(value,str(uuid4()))
            return value
        return remap(raw)

    def test_review_survives_fresh_repository_with_actor_audit(self):
        result=self.client.patch(f'/api/findings/{self.finding_id}', json={'status':'resolved','resolution':resolution()})
        self.assertEqual(result.status_code,200,result.text)
        fresh=PostgresRepository(TEST_URL)
        self.assertEqual(fresh.get_finding(self.finding_id).status,'resolved')
        audit=fresh.list_audit(self.study_id)
        self.assertEqual(len(audit),1)
        self.assertEqual(str(audit[0].entity_id),self.finding_id)
        self.assertEqual(audit[0].actor_id,DEMO_ACTOR_ID)
        self.assertEqual(self.client.patch(f'/api/findings/{self.finding_id}', json={'status':'resolved','resolution':resolution()}).status_code,200)
        self.assertEqual(len(fresh.list_audit(self.study_id)),1)

    def test_confirmation_requires_evidence_and_is_idempotent(self):
        with psycopg.connect(TEST_URL) as c:
            c.execute("UPDATE dependencies SET status='proposed', evidence='[]' WHERE id=%s",(self.edge_id,))
        path=f'/api/dependencies/{self.edge_id}'
        self.assertEqual(self.client.patch(path,json={'status':'confirmed'}).status_code,422)
        self.assertEqual(self.repository.list_audit(self.study_id),[])
        evidence=self.fixture['graph']['dependencies'][0]['evidence']
        with psycopg.connect(TEST_URL) as c:
            c.execute('UPDATE dependencies SET evidence=%s WHERE id=%s',(Jsonb(evidence),self.edge_id))
        for _ in range(2):
            response=self.client.patch(path,json={'status':'confirmed'})
            self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(PostgresRepository(TEST_URL).list_audit(self.study_id)),1)

    def test_audit_failure_rolls_back_review(self):
        with psycopg.connect(TEST_URL) as c:
            c.execute("""CREATE FUNCTION reject_review_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'test audit rejection'; END $$;
                CREATE TRIGGER reject_review_audit BEFORE INSERT ON audit_events
                FOR EACH ROW EXECUTE FUNCTION reject_review_audit()""")
        try:
            response=self.client.patch(f'/api/findings/{self.finding_id}',json={'status':'resolved','resolution':resolution()})
            self.assertEqual(response.status_code,503)
            self.assertEqual(self.repository.get_finding(self.finding_id).status,'open')
            self.assertEqual(self.repository.list_audit(self.study_id),[])
            # Rebinding and approval must also roll back if their audit append fails.
            protocol=next(a for a in self.fixture['artifacts'] if a['kind']=='protocol')
            graph_before=self.repository.get_graph(self.study_id)
            response=self.client.post(f'/api/versions/{protocol["versions"][-1]["id"]}/approve')
            self.assertEqual(response.status_code,503)
            self.assertEqual(self.repository.get_graph(self.study_id),graph_before)
            with psycopg.connect(TEST_URL) as c:
                approved=c.execute('SELECT approved_version_id FROM artifacts WHERE id=%s',(protocol['id'],)).fetchone()[0]
            self.assertEqual(str(approved),protocol['versions'][0]['id'])
        finally:
            with psycopg.connect(TEST_URL) as c:
                c.execute('DROP TRIGGER reject_review_audit ON audit_events; DROP FUNCTION reject_review_audit()')

    def test_concurrent_identical_reviews_append_one_audit(self):
        def review(_):
            repo=PostgresRepository(TEST_URL)
            return repo.update_finding(self.finding_id,FindingReview(status='resolved',resolution=resolution()),DEMO_ACTOR_ID,self.policy)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(review,range(4)))
        self.assertTrue(all(f.status=='resolved' for f in results))
        self.assertEqual(len(self.repository.list_audit(self.study_id)),1)

    def test_approval_preserves_history_pinned_and_unrelated_findings(self):
        protocol=next(a for a in self.fixture['artifacts'] if a['kind']=='protocol')
        replacement=protocol['versions'][-1]['id']
        before=self.repository.get_graph(self.study_id)
        findings=self.repository.list_findings(self.study_id)
        response=self.client.post(f'/api/versions/{replacement}/approve')
        self.assertEqual(response.status_code,200,response.text)
        after=self.repository.get_graph(self.study_id)
        self.assertEqual(len(after.dependencies),len(before.dependencies)+2)
        for old in before.dependencies:
            self.assertIn(old,after.dependencies)
        self.assertEqual(self.repository.list_findings(self.study_id),findings)
        self.assertEqual(self.client.post(f'/api/versions/{protocol["versions"][0]["id"]}/approve').status_code,409)

    def test_missing_projection_target_rolls_back_approval(self):
        protocol=next(a for a in self.fixture['artifacts'] if a['kind']=='protocol')
        candidate=str(uuid4())
        with psycopg.connect(TEST_URL) as c:
            c.execute("INSERT INTO artifact_versions(id,artifact_id,study_id,version_number,previous_version_id,filename,status) VALUES (%s,%s,%s,3,%s,'empty.json','ready')",
                (candidate,protocol['id'],self.study_id,protocol['versions'][-1]['id']))
        before=self.repository.get_graph(self.study_id)
        self.assertEqual(self.client.post(f'/api/versions/{candidate}/approve').status_code,409)
        self.assertEqual(self.repository.get_graph(self.study_id),before)
        self.assertEqual(self.repository.list_audit(self.study_id),[])

    def test_updated_requires_ready_newer_same_artifact_replacement(self):
        current=self.repository.get_finding(self.finding_id)
        wrong=next(a for a in self.fixture['artifacts'] if a['id']!=str(current.affected_artifact_id))['versions'][0]['id']
        path=f'/api/findings/{self.finding_id}'
        response=self.client.patch(path,json={'status':'resolved','resolution':resolution('updated',replacement_version_id=wrong)})
        self.assertEqual(response.status_code,422,response.text)
        artifact=next(a for a in self.fixture['artifacts'] if a['id']==str(current.affected_artifact_id))
        candidate=str(uuid4())
        with psycopg.connect(TEST_URL) as c:
            c.execute("INSERT INTO artifact_versions(id,artifact_id,study_id,version_number,previous_version_id,filename,status) VALUES (%s,%s,%s,2,%s,'updated.txt','uploaded')",
                (candidate,artifact['id'],self.study_id,artifact['versions'][0]['id']))
        patch={'status':'resolved','resolution':resolution('updated',replacement_version_id=candidate)}
        self.assertEqual(self.client.patch(path,json=patch).status_code,422)
        with psycopg.connect(TEST_URL) as c:
            c.execute("UPDATE artifact_versions SET status='ready' WHERE id=%s",(candidate,))
            for fact in self.fixture['graph']['facts']:
                if fact['artifact_id']==artifact['id']:
                    fragment_id, fact_id=str(uuid4()),str(uuid4())
                    c.execute('INSERT INTO source_fragments(id,study_id,artifact_id,version_id,locator,quote) VALUES (%s,%s,%s,%s,%s,%s)',
                        (fragment_id,self.study_id,artifact['id'],candidate,'revision:1','Updated to week 36'))
                    c.execute('INSERT INTO facts(id,study_id,artifact_id,version_id,fragment_id,logical_key,label,value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (fact_id,self.study_id,artifact['id'],candidate,fragment_id,fact['logical_key'],fact['label'],Jsonb(36),fact['unit']))
        response=self.client.patch(path,json=patch)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(PostgresRepository(TEST_URL).get_finding(self.finding_id).resolution.replacement_version_id,
                         self.repository.get_version(candidate).version.id)
        self.assertEqual(len(self.repository.list_audit(self.study_id)),2)
