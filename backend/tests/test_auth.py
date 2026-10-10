from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import httpx
import psycopg

from app.api.auth import AuthUnavailable, InvalidToken, SupabaseTokenVerifier
from app.main import create_app
from app.persistence.memory import InMemoryRepository
from app.persistence.postgres import PostgresRepository
from app.persistence.seed import DEMO_ACTOR_ID, DEMO_STUDY_ID, seed_demo
from app.persistence.storage import LocalPrivateStorage, configured_storage

TEST_URL = os.environ.get('TRIALSYNC_AUTH_TEST_DATABASE_URL')


class FixtureVerifier:
    """Test identity provider only; never selected by environment or production code."""
    def __init__(self, tokens):
        self.tokens = tokens
        self.calls = []

    def verify(self, token):
        self.calls.append(token)
        if token not in self.tokens:
            raise InvalidToken
        return self.tokens[token]


class SupabaseVerifierTest(unittest.TestCase):
    def test_server_verified_identity_ignores_editable_metadata(self):
        captured = []
        user_id = uuid4()
        def reply(request):
            captured.append(request)
            return httpx.Response(200, json={'id': str(user_id), 'aud':'authenticated', 'role':'authenticated',
                'user_metadata':{'study_id':str(DEMO_STUDY_ID),'role':'owner','user_id':str(DEMO_ACTOR_ID)}})
        with httpx.Client(transport=httpx.MockTransport(reply)) as client:
            verifier = SupabaseTokenVerifier('https://project.supabase.co','sb_publishable_test',client)
            self.assertEqual(verifier.verify('user-access-token'),user_id)
        self.assertEqual(str(captured[0].url),'https://project.supabase.co/auth/v1/user')
        self.assertEqual(captured[0].headers['apikey'],'sb_publishable_test')
        self.assertEqual(captured[0].headers['Authorization'],'Bearer user-access-token')

    def test_invalid_expired_foreign_and_privileged_tokens_rejected(self):
        for status in (401,403):
            with self.subTest(status=status), httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(status))) as client:
                verifier=SupabaseTokenVerifier('https://project.supabase.co','sb_publishable_test',client)
                for token in ('invalid','expired','foreign-project'):
                    with self.assertRaises(InvalidToken):verifier.verify(token)
        with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={
            'id':str(DEMO_ACTOR_ID),'aud':'authenticated','role':'service_role'}))) as client:
            verifier=SupabaseTokenVerifier('https://project.supabase.co','sb_publishable_test',client)
            with self.assertRaises(InvalidToken):verifier.verify('privileged-token')
            with self.assertRaises(InvalidToken):verifier.verify('sb_secret_backend')
            with self.assertRaises(InvalidToken):verifier.verify('sb_publishable_project')

    def test_outages_and_malformed_server_responses_fail_closed(self):
        for response in (httpx.Response(503,text='private diagnostics'),httpx.Response(200,json={'id':'broken'}),
                         httpx.Response(200,json={'id':'invalid','aud':'authenticated','role':'authenticated'})):
            with httpx.Client(transport=httpx.MockTransport(lambda _:response)) as client:
                verifier=SupabaseTokenVerifier('https://project.supabase.co','sb_publishable_test',client)
                with self.assertRaises((AuthUnavailable,InvalidToken)):verifier.verify('token')
        def timeout(request):raise httpx.ConnectError('private credentials',request=request)
        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            verifier=SupabaseTokenVerifier('https://project.supabase.co','sb_publishable_test',client)
            with self.assertRaises(AuthUnavailable):verifier.verify('token')

    def test_configuration_never_uses_elevated_key(self):
        for key in ('sb_secret_backend','legacy_service_role',''):
            with self.assertRaises(ValueError):SupabaseTokenVerifier('https://project.supabase.co',key)
        for url in ('http://project.supabase.co','https://user:password@project.supabase.co','https://project.supabase.co/path'):
            with self.assertRaises(ValueError):SupabaseTokenVerifier(url,'sb_publishable_test')
        with patch.dict(os.environ,{'SUPABASE_URL':'https://project.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'','SUPABASE_STORAGE_BUCKET':''}):
            self.assertIsInstance(configured_storage(),LocalPrivateStorage)


class AuthAPITest(unittest.TestCase):
    def setUp(self):
        self.repo=InMemoryRepository()
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage=LocalPrivateStorage(Path(self.directory.name))
        self.outsider=uuid4()
        self.verifier=FixtureVerifier({'member':DEMO_ACTOR_ID,'outsider':self.outsider})
        self.application=create_app(self.repo,storage=self.storage,auth_mode='required',token_verifier=self.verifier)
        self.client=TestClient(self.application)
        self.member={'Authorization':'Bearer member'}
        self.nonmember={'Authorization':'Bearer outsider'}
        self.artifact=self.repo.list_artifacts(DEMO_STUDY_ID)[0]
        self.finding=self.repo.list_findings(DEMO_STUDY_ID)[0]
        self.edge=self.repo.get_graph(DEMO_STUDY_ID).dependencies[0]

    def upload(self, headers=None):
        return self.client.post(f'/api/artifacts/{self.artifact.id}/versions',headers=headers or self.member,
            files={'file':('revision.txt',b'Synthetic private evidence','text/plain')})

    def test_default_requires_auth_even_without_configuration(self):
        with patch.dict(os.environ,{'TRIALSYNC_AUTH_MODE':'required','SUPABASE_PUBLISHABLE_KEY':''}):
            client=TestClient(create_app(self.repo,storage=self.storage))
        self.assertEqual(client.get('/health').status_code,200)
        response=client.get('/api/studies')
        self.assertEqual(response.status_code,401)
        self.assertEqual(response.headers['WWW-Authenticate'],'Bearer')
        self.assertEqual(client.get('/api/studies',headers=self.member).status_code,503)
        schema=client.get('/openapi.json').json()
        self.assertEqual(schema['components']['securitySchemes']['SupabaseBearer']['scheme'],'bearer')
        self.assertNotIn('security',schema['paths']['/health']['get'])
        for path,operations in schema['paths'].items():
            if path.startswith('/api/'):
                self.assertTrue(all(op['security']==[{'SupabaseBearer':[]}] for op in operations.values()))

    def test_missing_malformed_duplicate_and_invalid_auth_denied_everywhere(self):
        paths=['/api/studies']+[f'/api/studies/{DEMO_STUDY_ID}/{s}' for s in ('artifacts','graph','findings','audit')]
        paths += [f'/api/jobs/{uuid4()}',f'/api/versions/{self.artifact.versions[0].id}/source','/api/private-source']
        for path in paths:
            self.assertEqual(self.client.get(path).status_code,401,path)
        for headers in ({'Authorization':'Basic member'},{'Authorization':'Bearer '},
                        {'Authorization':'Bearer invalid'},{'Authorization':'Bearer member extra'},
                        [('Authorization','Bearer member'),('Authorization','Bearer outsider')]):
            self.assertEqual(self.client.get('/api/studies',headers=headers).status_code,401)
        self.assertEqual(self.client.post(f'/api/artifacts/{self.artifact.id}/versions').status_code,401)
        self.assertEqual(self.client.patch(f'/api/findings/{self.finding.id}',json={'status':'in_review'}).status_code,401)
        self.assertEqual(self.client.patch(f'/api/dependencies/{self.edge.id}',json={'status':'confirmed'}).status_code,401)
        self.assertEqual(self.client.post(f'/api/versions/{self.artifact.versions[0].id}/approve').status_code,401)

    def test_only_member_studies_and_read_routes_are_visible(self):
        self.assertEqual(self.client.get('/api/studies',headers=self.nonmember).json(),{'items':[]})
        self.assertEqual(len(self.client.get('/api/studies',headers=self.member).json()['items']),1)
        for suffix in ('artifacts','graph','findings','audit'):
            path=f'/api/studies/{DEMO_STUDY_ID}/{suffix}'
            self.assertEqual(self.client.get(path,headers=self.nonmember).status_code,403)
            self.assertEqual(self.client.get(path,headers=self.member).status_code,200)

    def test_nonmembers_cannot_upload_review_confirm_or_approve(self):
        before=self.repo.list_audit(DEMO_STUDY_ID)
        self.assertEqual(self.upload(self.nonmember).status_code,403)
        self.assertEqual(self.client.patch(f'/api/findings/{self.finding.id}',headers=self.nonmember,json={'status':'in_review'}).status_code,403)
        self.assertEqual(self.client.patch(f'/api/dependencies/{self.edge.id}',headers=self.nonmember,json={'status':'confirmed'}).status_code,403)
        self.assertEqual(self.client.post(f'/api/versions/{self.artifact.versions[-1].id}/approve',headers=self.nonmember).status_code,403)
        self.assertEqual(self.repo.list_audit(DEMO_STUDY_ID),before)
        self.assertEqual(list(Path(self.directory.name).rglob('*')),[])

    def test_job_sign_and_private_download_check_current_membership(self):
        response=self.upload();self.assertEqual(response.status_code,201,response.text)
        upload=response.json()
        job=f"/api/jobs/{upload['job']['id']}"
        source=f"/api/versions/{upload['version']['id']}/source"
        for path in (job,source):
            self.assertEqual(self.client.get(path,headers=self.nonmember).status_code,403)
            self.assertEqual(self.client.get(path,headers=self.member).status_code,200)
        signed=self.client.get(source,headers=self.member)
        self.assertEqual(signed.headers['Cache-Control'],'private, no-store')
        url=signed.json()['url']
        self.assertEqual(self.client.get(url).status_code,401)
        self.assertEqual(self.client.get(url,headers=self.nonmember).status_code,403)
        self.assertEqual(self.client.get(url,headers=self.member).content,b'Synthetic private evidence')
        self.repo._members[DEMO_STUDY_ID].remove(DEMO_ACTOR_ID)
        for path in (job,source,url):
            self.assertEqual(self.client.get(path,headers=self.member).status_code,403)

    def test_audit_actor_comes_from_verified_user_not_app_or_request(self):
        self.application.state.review_actor=self.outsider
        path=f'/api/findings/{self.finding.id}'
        self.assertEqual(self.client.patch(path,headers=self.member,json={'status':'in_review','actor_id':str(self.outsider)}).status_code,422)
        response=self.client.patch(path,headers=self.member,json={'status':'in_review'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.repo.list_audit(DEMO_STUDY_ID)[-1].actor_id,DEMO_ACTOR_ID)
        self.assertEqual(self.verifier.calls.count('member'),2)  # Once per request, despite multiple dependencies.

    def test_upload_auth_rejects_before_reading_or_parsing(self):
        import asyncio
        async def run(headers):
            received=0;messages=[]
            async def receive():
                nonlocal received
                received+=1
                raise AssertionError('Unauthorized upload body must not be read')
            async def send(message):messages.append(message)
            await self.application({'type':'http','http_version':'1.1','method':'POST','scheme':'http',
                'path':f'/api/artifacts/{self.artifact.id}/versions','query_string':b'','headers':headers,
                'server':('testserver',80),'client':('127.0.0.1',123),'root_path':''},receive,send)
            self.assertEqual(received,0)
            return next(m['status'] for m in messages if m['type']=='http.response.start')
        self.assertEqual(asyncio.run(run([])),401)
        self.assertEqual(asyncio.run(run([(b'authorization',b'Bearer outsider')])),403)

    def test_exact_cors_allows_bearer_and_patch_without_opening_wildcards(self):
        with patch.dict(os.environ,{'CORS_ORIGINS':'https://trialsync.example'}):
            client=TestClient(create_app(self.repo,storage=self.storage,auth_mode='required',token_verifier=self.verifier))
        request={'Origin':'https://trialsync.example','Access-Control-Request-Method':'PATCH',
                 'Access-Control-Request-Headers':'authorization,content-type'}
        response=client.options(f'/api/findings/{self.finding.id}',headers=request)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://trialsync.example')
        request['Origin']='https://other.example'
        self.assertEqual(client.options('/api/studies',headers=request).status_code,400)
        self.assertNotIn('Access-Control-Allow-Origin',client.get('/api/studies',headers=self.member|{'Origin':'https://other.example'}).headers)
        with patch.dict(os.environ,{'CORS_ORIGINS':'*'}):
            with self.assertRaises(ValueError):create_app(self.repo,storage=self.storage)


@unittest.skipUnless(TEST_URL,'Set TRIALSYNC_AUTH_TEST_DATABASE_URL to an empty disposable database')
class PostgresAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(TEST_URL) as connection:
            if not connection.execute('SELECT current_database()').fetchone()[0].startswith('trialsync_test'):
                raise RuntimeError('Auth tests require a disposable trialsync_test* database')
            if connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError('Existing data is never reset')
            for path in sorted((Path(__file__).resolve().parents[2]/'supabase/migrations').glob('*.sql')):
                connection.execute(path.read_text())
        seed_demo(TEST_URL)

    def test_real_membership_is_scoped_live_and_audit_uses_authenticated_actor(self):
        repository=PostgresRepository(TEST_URL)
        member=uuid4();nonmember=uuid4();other_study=uuid4()
        with psycopg.connect(TEST_URL) as c:
            c.execute("INSERT INTO studies(id,name) VALUES (%s,'Other auth study')",(other_study,))
            c.execute("INSERT INTO memberships(study_id,user_id,role) VALUES (%s,%s,'member')",(DEMO_STUDY_ID,member))
            c.execute("INSERT INTO memberships(study_id,user_id,role) VALUES (%s,%s,'member')",(other_study,nonmember))
        verifier=FixtureVerifier({'member':member,'outsider':nonmember})
        with TemporaryDirectory() as folder:
            storage=LocalPrivateStorage(Path(folder))
            client=TestClient(create_app(repository,storage=storage,auth_mode='required',token_verifier=verifier))
            auth={'Authorization':'Bearer member'};outsider={'Authorization':'Bearer outsider'}
            listed=client.get('/api/studies',headers=auth).json()['items']
            self.assertEqual([i['id'] for i in listed],[str(DEMO_STUDY_ID)])
            self.assertEqual(client.get(f'/api/studies/{other_study}/graph',headers=auth).status_code,403)
            artifact=repository.list_artifacts(DEMO_STUDY_ID)[0]
            response=client.post(f'/api/artifacts/{artifact.id}/versions',headers=auth,
                files={'file':('private.txt',b'private bytes','text/plain')})
            self.assertEqual(response.status_code,201,response.text)
            upload=response.json()
            for suffix in (f"/api/jobs/{upload['job']['id']}",f"/api/versions/{upload['version']['id']}/source"):
                self.assertEqual(client.get(suffix,headers=outsider).status_code,403)
                self.assertEqual(client.get(suffix,headers=auth).status_code,200)
            source=f"/api/versions/{upload['version']['id']}/source"
            signed=client.get(source,headers=auth).json()['url']
            finding=repository.list_findings(DEMO_STUDY_ID)[0]
            response=client.patch(f'/api/findings/{finding.id}',headers=auth,json={'status':'in_review','owner_id':str(member)})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(PostgresRepository(TEST_URL).list_audit(DEMO_STUDY_ID)[-1].actor_id,member)
            with psycopg.connect(TEST_URL) as c:
                c.execute('DELETE FROM memberships WHERE study_id=%s AND user_id=%s',(DEMO_STUDY_ID,member))
            for path in (source,signed,f"/api/jobs/{upload['job']['id']}",f'/api/studies/{DEMO_STUDY_ID}/audit'):
                self.assertEqual(client.get(path,headers=auth).status_code,403)
            self.assertEqual(client.get('/api/studies',headers=auth).json(),{'items':[]})
