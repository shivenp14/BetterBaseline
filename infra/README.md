# Render API and worker deployment

Issue #19 preparation: deploy **both processes at the same reviewed commit**.
This branch is stacked on #49 (authentication), #46, #45, and #43. Do not
expose the earlier unauthenticated branches. Hosted deployment has not yet
been performed: no Render workspace/services, Supabase project credentials,
or real user token are available in this workspace. Fill the result record
below after deployment and the smoke check; issue #19 remains incomplete until then.

## Services

Create a Python Web Service and a separate Background Worker in the intended
Render workspace, connected to `shivenp14/TrialSync`. Use root directory
`backend`, Python 3.12, build command `pip install .`, and these start commands:

| Service | Start command | Health check |
| --- | --- | --- |
| API | `python -m app.deploy api` | `/ready` |
| Worker (one instance) | `python -m app.deploy worker` | No HTTP URL/check; inspect process logs and completed jobs |

The API binds `0.0.0.0` on Render's `PORT` (default 10000). `/health` is
liveness; `/ready` uses a bounded database read to verify baseline and worker
schema availability. Startup also checks private bucket access. External Auth
and Storage availability after startup are verified by the authenticated smoke
flow, rather than repeatedly probing those services from health checks.

Do not use the local `trialsync-api` loopback command for hosting. Disable
automatic deploys while preparing the stack; select the reviewed branch/commit
and enable deployment after the prerequisites are ready. No Blueprint or
infrastructure platform is required.

## Private environment configuration

Set variables in Render's private service environment, never in git, build
arguments, frontend public variables, or pasted logs. API and worker must share
the same database, project and private bucket. Keep the database unexposed to
browser roles; existing migrations enable RLS without browser policies.

| Variable | Value / process |
| --- | --- |
| `DATABASE_URL` | Backend PostgreSQL URL with explicit `sslmode=require` or stronger; both |
| `SUPABASE_URL` | HTTPS project origin; both |
| `SUPABASE_PUBLISHABLE_KEY` | Project publishable key for Auth verification; both |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend-only Storage credential; both |
| `SUPABASE_STORAGE_BUCKET` | Existing **private** bucket, e.g. `trialsync-private`; both |
| `CORS_ORIGINS` | Comma-separated exact HTTPS frontend origins; both |
| `TRIALSYNC_AUTH_MODE` | `required`; both (demo mode is refused) |
| `TRIALSYNC_WORKER_ADAPTER` | Explicit `demo` for this synthetic JSON rehearsal, or reviewed `module:factory`; worker |
| `TRIALSYNC_DEMO_USER_ID` | Real Supabase Auth user's UUID; operator seed session only |

Use the session pooler or direct PostgreSQL endpoint reachable from Render;
`prepare_threshold=None` avoids prepared-statement incompatibilities. Never use
an Auth API key as a user access token. A real authenticated user's UUID must
have a database membership. `demo` selects synthetic **processing**, while API
authentication stays required. This adapter accepts strict JSON, not PDFs;
live ingestion/domain integration remains #25/#32.

## Migrate and seed once

From an operator shell at the reviewed commit, with the private environment
already configured, apply the two existing migrations in filename order to the
intended database. For an empty database only:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f supabase/migrations/20261010203734_baseline.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 -f supabase/migrations/20261010230000_worker_candidate_changes.sql
python -m app.deploy seed
```

Run the Python command from `backend` after `pip install .`; migration paths
above are relative to the repository root. Inspect existing migration history
first; these SQL files are not safe to rerun blindly. This PR adds no migration.
`seed` inserts only the fixed synthetic study and the explicit real user's
membership. Repeating it retains reviews, uploads and existing memberships; it
does not delete or reset any study. It does not create Supabase Auth users: create
a rehearsal user through the project's normal Auth flow first.

## Hosted verification

After starting both services, sign in normally to obtain a short-lived user
access token. In a private operator session with backend dependencies installed,
set `TRIALSYNC_API_URL` to the API's HTTPS origin, `TRIALSYNC_ACCESS_TOKEN` to
that token, and `SUPABASE_URL` to the project origin, then run from repo root:

```sh
python infra/smoke.py
```

The script checks readiness, missing-token rejection, member artifact access,
uploads a week-36 synthetic protocol revision, polls the separate worker,
and compares a private source download with the uploaded bytes. It intentionally
creates a new version/job; repeated runs preserve history. It does not approve
the candidate, reset data, or print credentials/signed URLs. With another
signed-in nonmember, confirm study, job and source API requests return 403.
Restart the worker and repeat job polling: a succeeded job remains succeeded;
running jobs recover under the existing lease rules. See
[WORKER.md](../backend/app/persistence/WORKER.md) for the recovery procedure.

Record:

| Evidence | Result |
| --- | --- |
| Reviewed commit | Pending |
| API HTTPS URL | Pending service creation |
| Worker Render dashboard/service ID | Pending service creation (no HTTP URL) |
| Private project/bucket configured | Pending |
| Authenticated upload/job/source verification | Pending |
| Missing-token and nonmember denial | Pending hosted verification |

References: [Render FastAPI](https://render.com/docs/deploy-fastapi),
[workers](https://render.com/docs/background-workers),
[health checks](https://render.com/docs/health-checks),
[Auth setup](../backend/app/api/AUTH.md).
