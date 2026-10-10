import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import psycopg

from app.api.uploads import MAX_UPLOAD_BYTES, StudyAccessDenied
from app.main import create_app
from app.persistence.memory import InMemoryRepository
from app.persistence.postgres import PostgresRepository
from app.persistence.repository import RepositoryUnavailable, UploadOutcomeUnknown
from app.persistence.seed import DEMO_STUDY_ID, seed_demo
from app.persistence.storage import LocalPrivateStorage, ObjectAlreadyExists, StorageUnavailable, SupabasePrivateStorage


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repository = InMemoryRepository()
        self.storage = LocalPrivateStorage(Path(self.directory.name), signing_key=b"test-signing-key")
        self.client = TestClient(create_app(self.repository, self.storage))
        self.artifact = next(item for item in self.repository.list_artifacts(DEMO_STUDY_ID) if len(item.versions) == 1)
        self.route = f"/api/artifacts/{self.artifact.id}/versions"

    def upload(self, content=b"Updated endpoint: week 36", name="revision.txt"):
        return self.client.post(self.route, files={"file": (name, content, "text/plain")})

    def test_upload_preserves_history_hash_and_queued_job(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["version"]["version_number"], 2)
        self.assertEqual(body["version"]["previous_version_id"], str(self.artifact.versions[0].id))
        self.assertEqual(body["version"]["status"], "uploaded")
        self.assertEqual(body["job"]["status"], "queued")
        self.assertEqual(self.client.get(f'/api/jobs/{body["job"]["id"]}').json(), body["job"])
        versions = self.repository.get_artifact(self.artifact.id).versions
        self.assertEqual(versions[0], self.artifact.versions[0])
        stored = self.repository.get_version(versions[-1].id)
        self.assertEqual(stored.content_hash, hashlib.sha256(b"Updated endpoint: week 36").hexdigest())
        self.assertEqual((self.storage.root / stored.storage_path).read_bytes(), b"Updated endpoint: week 36")

    def test_unique_paths_same_filename_and_source_capabilities(self):
        first = self.upload().json()
        second = self.upload(b"another revision").json()
        self.assertNotEqual(first["version"]["id"], second["version"]["id"])
        self.assertEqual(second["version"]["version_number"], 3)
        url = self.client.get(f'/api/versions/{first["version"]["id"]}/source').json()["url"]
        self.assertEqual(self.client.get(url).content, b"Updated endpoint: week 36")
        self.assertEqual(self.client.get(url + "corrupt").status_code, 403)
        with patch("app.persistence.storage.time.time", return_value=10**12):
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get("/api/private-source", params={"path": "../outside", "expires": 10**12,
                                                                     "signature": "forged"}).status_code, 403)

    def test_empty_oversized_unknown_and_filename_handling(self):
        self.assertEqual(self.upload(b"").status_code, 422)
        self.assertEqual(self.upload(b"x" * (MAX_UPLOAD_BYTES + 1)).status_code, 413)
        self.assertEqual(list(self.storage.root.rglob("*")), [])
        self.assertEqual(self.client.post(f"/api/artifacts/{uuid4()}/versions",
            files={"file": ("revision.txt", b"body")}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/jobs/{uuid4()}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/versions/{uuid4()}/source").status_code, 404)
        response = self.upload(name="../../revision.txt")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["version"]["filename"], "revision.txt")

    def test_study_policy_precedes_upload_poll_and_signing(self):
        body = self.upload().json()
        class Deny:
            def require_study_access(self, study_id):
                raise StudyAccessDenied
        client = TestClient(create_app(self.repository, self.storage, Deny()))
        with patch.object(self.storage, "signed_url", wraps=self.storage.signed_url) as sign:
            self.assertEqual(client.get(f'/api/versions/{body["version"]["id"]}/source').status_code, 403)
            sign.assert_not_called()
        self.assertEqual(client.get(f'/api/jobs/{body["job"]["id"]}').status_code, 403)
        self.assertEqual(client.post(self.route, files={"file": ("denied.txt", b"denied")}).status_code, 403)
        self.assertEqual(len(list(self.storage.root.rglob("*.txt"))), 1)

    def test_database_failure_removes_new_object_and_no_version(self):
        with patch.object(self.repository, "create_version_job", side_effect=RepositoryUnavailable):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(len(self.repository.get_artifact(self.artifact.id).versions), 1)
        self.assertEqual(list(self.storage.root.rglob("*.txt")), [])

    def test_uncertain_storage_failure_does_not_delete_unowned_object(self):
        put = self.storage.put
        def partial(*args):
            put(*args)
            raise StorageUnavailable
        with patch.object(self.storage, "put", side_effect=partial):
            with patch.object(self.storage, "delete") as remove:
                with self.assertLogs("app.api.uploads", level="ERROR"):
                    self.assertEqual(self.upload().status_code, 503)
                remove.assert_not_called()
        self.assertEqual(len(list(self.storage.root.rglob("*.txt"))), 1)

    def test_cleanup_failure_is_reported_for_reconciliation(self):
        with patch.object(self.repository, "create_version_job", side_effect=RepositoryUnavailable):
            with patch.object(self.storage, "delete", side_effect=StorageUnavailable):
                with self.assertLogs("app.api.uploads", level="ERROR"):
                    response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn("cleanup needs reconciliation", response.json()["error"]["message"])

    def test_uncertain_commit_retains_object_for_reconciliation(self):
        with patch.object(self.repository, "create_version_job", side_effect=UploadOutcomeUnknown):
            with self.assertLogs("app.api.uploads", level="ERROR"):
                response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIn("outcome unknown", response.json()["error"]["message"])
        self.assertEqual(len(list(self.storage.root.rglob("*.txt"))), 1)

    def test_collision_does_not_delete_existing_object(self):
        with patch.object(self.storage, "put", side_effect=ObjectAlreadyExists):
            with patch.object(self.storage, "delete") as remove:
                self.assertEqual(self.upload().status_code, 503)
                remove.assert_not_called()

    def test_supabase_duplicate_and_failed_put_never_delete_existing_object(self):
        for status, body in [(400, {"statusCode": "400", "error": "Duplicate", "message": "The resource already exists"}),
                             (400, {"message": "Asset Already Exists"}), (409, {}),
                             (400, {"message": "Other failure"}), (500, {})]:
            with self.subTest(status=status, body=body):
                requests = []
                def handler(request):
                    requests.append(request)
                    if request.method == "GET":
                        return httpx.Response(200, json={"public": False})
                    return httpx.Response(status, json=body)
                with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
                    storage = SupabasePrivateStorage("https://project.test", "test-key", "private", remote)
                    client = TestClient(create_app(self.repository, storage))
                    response = client.post(self.route, files={"file": ("revision.txt", b"body")})
                self.assertEqual(response.status_code, 503)
                self.assertEqual([r.method for r in requests], ["GET", "POST"])
                self.assertEqual(len(self.repository.get_artifact(self.artifact.id).versions), 1)


class SupabaseStorageTest(unittest.TestCase):
    def test_private_upload_sign_and_delete_http_contract(self):
        requests = []
        def handler(request):
            requests.append(request)
            if "/bucket/" in request.url.path:
                return httpx.Response(200, json={"public": False})
            if "/sign/" in request.url.path:
                self.assertEqual(json.loads(request.content), {"expiresIn": 60})
                return httpx.Response(200, json={"signedURL": "/object/sign/private/path?token=capability"})
            return httpx.Response(200, json={})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            storage = SupabasePrivateStorage("https://project.test", "test-key", "private", client)
            storage.put("study/version/revision.txt", b"body", "text/plain")
            self.assertEqual(requests[-1].headers["x-upsert"], "false")
            self.assertEqual(requests[-1].headers["content-type"], "text/plain")
            self.assertEqual(requests[-1].content, b"body")
            self.assertEqual(storage.signed_url("study/version/revision.txt", ""),
                             "https://project.test/storage/v1/object/sign/private/path?token=capability")
            storage.delete("study/version/revision.txt")
            self.assertEqual(requests[-1].method, "DELETE")
            self.assertEqual(json.loads(requests[-1].content), {"prefixes": ["study/version/revision.txt"]})

    def test_public_bucket_is_rejected(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"public": True})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            storage = SupabasePrivateStorage("https://project.test", "test-key", "public", client)
            with self.assertRaises(StorageUnavailable):
                storage.put("path", b"body", "text/plain")
        self.assertEqual(len(requests), 1)


UPLOAD_TEST_URL = os.environ.get("TRIALSYNC_UPLOAD_TEST_DATABASE_URL")


@unittest.skipUnless(UPLOAD_TEST_URL, "Set TRIALSYNC_UPLOAD_TEST_DATABASE_URL to an empty disposable database")
class PostgresUploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(UPLOAD_TEST_URL) as connection:
            name = connection.execute("SELECT current_database()").fetchone()[0]
            if not name.startswith("trialsync_test") or connection.execute("SELECT to_regclass('public.studies')").fetchone()[0]:
                raise RuntimeError("Upload tests require an empty trialsync_test* database")
            for migration in sorted((Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql")):
                connection.execute(migration.read_text())
        seed_demo(UPLOAD_TEST_URL)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = LocalPrivateStorage(Path(self.directory.name))
        self.repository = PostgresRepository(UPLOAD_TEST_URL)
        self.client = TestClient(create_app(self.repository, self.storage))
        self.artifact = next(item for item in self.repository.list_artifacts(DEMO_STUDY_ID) if item.kind == "analysis_plan")

    def test_upload_is_durable_and_leaves_approved_version_unchanged(self):
        before = self.artifact.versions
        response = self.client.post(f"/api/artifacts/{self.artifact.id}/versions", files={"file": ("revision.txt", b"week 36")})
        self.assertEqual(response.status_code, 201)
        body = response.json()
        fresh = PostgresRepository(UPLOAD_TEST_URL)
        self.assertEqual(str(fresh.get_job(body["job"]["id"]).job.id), body["job"]["id"])
        versions = fresh.get_artifact(self.artifact.id).versions
        self.assertEqual(versions[:-1], before)
        stored = fresh.get_version(versions[-1].id)
        self.assertEqual(stored.content_hash, hashlib.sha256(b"week 36").hexdigest())
        with psycopg.connect(UPLOAD_TEST_URL) as connection:
            approved = connection.execute("SELECT approved_version_id FROM artifacts WHERE id = %s", (self.artifact.id,)).fetchone()[0]
        self.assertEqual(approved, before[0].id)

    def test_concurrent_uploads_allocate_distinct_sequential_versions(self):
        before = self.repository.get_artifact(self.artifact.id).versions[-1].version_number
        def upload(number):
            with TestClient(create_app(PostgresRepository(UPLOAD_TEST_URL), self.storage)) as client:
                return client.post(f"/api/artifacts/{self.artifact.id}/versions",
                                   files={"file": ("same.txt", str(number).encode())})
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(upload, range(3)))
        self.assertTrue(all(result.status_code == 201 for result in results))
        self.assertEqual(sorted(result.json()["version"]["version_number"] for result in results),
                         list(range(before + 1, before + 4)))

    def test_job_insert_failure_rolls_back_version_and_cleans_file(self):
        before = len(self.repository.get_artifact(self.artifact.id).versions)
        # Force a database constraint failure after the version INSERT, using a test-only trigger.
        with psycopg.connect(UPLOAD_TEST_URL) as connection:
            connection.execute("""CREATE FUNCTION public.reject_test_job() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'test job rejection'; END $$;
                CREATE TRIGGER reject_test_job BEFORE INSERT ON public.jobs FOR EACH ROW EXECUTE FUNCTION public.reject_test_job()""")
        try:
            with TestClient(create_app(PostgresRepository(UPLOAD_TEST_URL), self.storage)) as client:
                response = client.post(f"/api/artifacts/{self.artifact.id}/versions", files={"file": ("failed.txt", b"body")})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(len(self.repository.get_artifact(self.artifact.id).versions), before)
            self.assertEqual(list(self.storage.root.rglob("*.txt")), [])
        finally:
            with psycopg.connect(UPLOAD_TEST_URL) as connection:
                connection.execute("DROP TRIGGER reject_test_job ON public.jobs; DROP FUNCTION public.reject_test_job()")
