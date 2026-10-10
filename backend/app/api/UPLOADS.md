# Version upload and polling (#15)

`pranav15` targets `pranav14` (#40); it uses the existing #14 schema and adds no
migration. Reinstall `./backend[test]` to get the multipart/runtime dependencies.
The API stays on `127.0.0.1:8000` until #18 implements authentication.

| Route | Response |
| --- | --- |
| `POST /api/artifacts/{artifact_id}/versions` | HTTP 201 `{version:ArtifactVersion,job:Job}` |
| `GET /api/jobs/{job_id}` | `{id,version_id,status,stage,error}` |
| `GET /api/versions/{version_id}/source` | `{url}` with a 60-second source capability |

Upload one multipart field named `file`, nonempty and at most 10 MiB. Filename
directories are stripped, invalid/control filenames rejected, and storage keys
include study/artifact/new-version UUIDs. Files are immutable, never upserted.
SHA-256 and the private key are stored internally, not exposed in the public
version response. Same-filename uploads use distinct keys.

PostgreSQL locks the artifact while allocating the next version number, then
inserts the new version and queued job in one transaction. Previous versions,
files, approved-version pointers, facts, and graph edges remain unchanged. Jobs
stay queued until #16 supplies the worker. The fixture's protocol already has
v1/v2 snapshots, so its next upload becomes v3; a v1-only analysis/schedule/report
artifact creates v2. Fixture-mode uploads/jobs live in memory and reset with the
process; PostgreSQL records survive restart.

## Private storage and access handoff

By default objects are written to `backend/.private-uploads/`, with private file
permissions, and downloaded only through HMAC-signed, expiring URLs. This folder
is excluded from Git. `LOCAL_STORAGE_ROOT` can select a persistent private folder.
Local signing keys are process-scoped: restart invalidates previously issued
URLs; clients can request fresh ones. No static file mount exposes this folder.
Fixture baseline versions have no actual source files and return 404 for source
requests; newly uploaded versions can be downloaded.

To use Supabase, set backend-only `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
(legacy backend service-role JWT), and `SUPABASE_STORAGE_BUCKET` together. The
adapter requires an existing private bucket and verifies `public=false` before
upload/signing. It never provisions a bucket or uses public object URLs. Requests
use the verified Storage upload/sign/remove routes and `x-upsert=false`. A partial
configuration fails explicitly. Hosted bucket credentials/integration were not
available during local verification.

`app.persistence.storage.PrivateStorage` defines `put`, `delete`, and `signed_url`.
`app.persistence.repository.UploadRepository` adds `get_artifact`,
`create_version_job`, `get_job`, and `get_version` to the read port. Stored
job/version wrappers include the study ID required by access checks; source paths
are kept internal.

All three public upload/job/source routes call
`StudyAccess.require_study_access(study_id)` before writing, returning a job, or
issuing a URL. Inject a policy into `create_app(..., study_access=policy)` or
override `app.api.uploads.get_study_access` with a request-specific policy in #18.
The current `LocalDemoAccess` is deliberately permissive for the local synthetic
demo; it is not authentication. Read-route protection and token validation are
#18's remaining work. Signed downloads are bearer capabilities, valid only until
expiry, rather than public storage objects.

## Failure handling

Rolled-back database writes after a successful storage PUT trigger deletion of
the new object. Failed or uncertain storage writes never authorize deletion of
an object this attempt did not confirm creating; retain it for reconciliation.
Duplicate paths (including Supabase HTTP 400 and 409) never delete existing objects. Cleanup failures
return 503 and log the object key for reconciliation. A connection error during
COMMIT has an uncertain outcome: retain the object and report/log version and job
IDs, rather than risk deleting a file whose version committed. Check those IDs
and remove an orphan only after establishing that no committed row uses it.
This is compensation for handled failures, not crash recovery; process termination
between storage and database writes can leave an orphan. Automated reconciliation
is outside #15. API errors use the shared envelope and do not include credentials
or raw SQL errors.

## Walkthrough and verification

Start the seeded PostgreSQL API as documented in `app/persistence/README.md`, or
use fixture mode. Read `/api/studies` and that study's `/artifacts` to get an ID:

```sh
curl -F 'file=@/path/to/synthetic-revision.txt' \
  http://127.0.0.1:8000/api/artifacts/ARTIFACT_UUID/versions
curl http://127.0.0.1:8000/api/jobs/JOB_UUID
curl http://127.0.0.1:8000/api/versions/VERSION_UUID/source
```

Verify the job is queued, the returned URL downloads the uploaded bytes, and the
artifact's previous versions remain. Upload a second file with the same name and
verify a different version/path. No auth token is used in this local slice.

Database tests need **two empty disposable databases** named `trialsync_test*`:
set `TRIALSYNC_TEST_DATABASE_URL` for baseline/read tests and
`TRIALSYNC_UPLOAD_TEST_DATABASE_URL` for upload tests, then run
`python -m unittest discover -s tests -v` from `backend`. Tests cover concurrent
number allocation, transactional rollback/cleanup, history/approval preservation,
content hashes, queued-job reads, signed-URL tampering/expiry, policy denial,
upload bounds, private-bucket enforcement, and Supabase HTTP request shapes.
# Incoming body bound

Upload streams are byte-counted before multipart parsing, including when
Content-Length is missing, invalid, or underreported. The total request envelope
is capped at 10 MiB plus 64 KiB for multipart headers/boundaries; the file itself
still has the 10 MiB route limit. Declared oversized requests are rejected before
reading. A stream that exceeds the envelope stops parsing immediately, closes
temporary multipart files, and returns 413 without creating an object or job.
