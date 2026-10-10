import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg

from app.deploy import database_ready, hosted_app, seed_member, validate_hosted_config
from app.persistence.seed import DEMO_STUDY_ID
from app.persistence.storage import SupabasePrivateStorage

CONFIG = {'DATABASE_URL': 'postgresql://user:password@database.test/db?sslmode=require',
          'SUPABASE_URL': 'https://project.test', 'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_fixture',
          'SUPABASE_SERVICE_ROLE_KEY': 'fixture-only-key', 'SUPABASE_STORAGE_BUCKET': 'private',
          'CORS_ORIGINS': 'https://web.test', 'TRIALSYNC_AUTH_MODE': 'required'}


class DeploymentTest(unittest.TestCase):
    def test_hosted_configuration_refuses_local_fallbacks(self):
        with patch.dict(os.environ, CONFIG, clear=True):
            self.assertIsInstance(validate_hosted_config(), SupabasePrivateStorage)
            for name in CONFIG:
                if name == 'TRIALSYNC_AUTH_MODE':
                    continue
                with self.subTest(missing=name), patch.dict(os.environ, {name: ''}):
                    with self.assertRaises(ValueError): validate_hosted_config()
            for values in ({'TRIALSYNC_AUTH_MODE': 'demo'}, {'CORS_ORIGINS': '*'},
                           {'CORS_ORIGINS': 'http://localhost:3000'},
                           {'DATABASE_URL': 'postgresql://user@database.test/db'},
                           {'SUPABASE_URL': 'http://project.test'}):
                with self.subTest(values=values), patch.dict(os.environ, values):
                    with self.assertRaises(ValueError): validate_hosted_config()

    def test_readiness_and_auth_remain_separate_and_errors_are_sanitized(self):
        with patch.dict(os.environ, CONFIG, clear=True):
            client = TestClient(hosted_app())
            with patch('app.deploy.database_ready') as ready:
                self.assertEqual(client.get('/ready').json(), {'status': 'ready'})
                ready.assert_called_once()
            with patch('app.deploy.database_ready', side_effect=psycopg.OperationalError('SECRET database credential')):
                response = client.get('/ready')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {'status': 'unavailable'})
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.get('/api/studies').status_code, 401)

    def test_invalid_member_is_rejected_before_seed_writes(self):
        with patch('app.deploy.seed_demo') as seed:
            with self.assertRaises(ValueError): seed_member('unused', 'invalid')
            seed.assert_not_called()


TEST_URL = os.environ.get('TRIALSYNC_DEPLOY_TEST_DATABASE_URL')


@unittest.skipUnless(TEST_URL, 'Set TRIALSYNC_DEPLOY_TEST_DATABASE_URL to an empty disposable database')
class PostgresDeploymentTest(unittest.TestCase):
    def test_schema_readiness_and_repeated_member_seed_preserve_data(self):
        with psycopg.connect(TEST_URL) as connection:
            if not connection.execute('SELECT current_database()').fetchone()[0].startswith('trialsync_test'):
                raise RuntimeError('Deployment test requires disposable trialsync_test* database')
            if connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError('Existing data is never reset')
            for path in sorted((Path(__file__).resolve().parents[2]/'supabase/migrations').glob('*.sql')):
                connection.execute(path.read_text())
        user = uuid4()
        self.assertEqual(seed_member(TEST_URL, user), DEMO_STUDY_ID)
        with psycopg.connect(TEST_URL) as connection:
            connection.execute("UPDATE findings SET status='in_review' WHERE study_id=%s", (DEMO_STUDY_ID,))
            audit_count = connection.execute('SELECT count(*) FROM audit_events').fetchone()[0]
        seed_member(TEST_URL, user)
        with patch.dict(os.environ, {'DATABASE_URL': TEST_URL}): database_ready()
        with psycopg.connect(TEST_URL) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM memberships WHERE study_id=%s AND user_id=%s',
                                               (DEMO_STUDY_ID, user)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM findings WHERE status='in_review'").fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM audit_events').fetchone()[0], audit_count)
