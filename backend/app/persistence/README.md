# PostgreSQL reads and synthetic seed (#14)

This PR stacks on #13 (`pranav13`). One migration creates studies/memberships,
artifacts/versions, source fragments/facts, dependencies, changes/findings,
audit events, and jobs. The five read routes keep the #13 HTTP shapes.

Install the shared backend package as described in `app/api/README.md`. Set
`DATABASE_URL` privately in the backend process to select `PostgresRepository`;
when it is absent/empty the API still uses `InMemoryRepository`. Environment
files are not loaded automatically. The server still binds `127.0.0.1:8000`.

## Apply and seed

From the repository root, with a database owner's connection string already
set in your environment:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction \
  -f supabase/migrations/20261010203734_baseline.sql
backend/.venv/bin/trialsync-seed
backend/.venv/bin/trialsync-api
```

Apply the migration once to an empty application schema. Startup and seeding
never auto-apply migrations. On Supabase, obtain the direct or session pooler
PostgreSQL connection from the project's Connect dialog, with verified TLS
and the appropriate CA. The adapter disables prepared statements for pooler
compatibility. Use an owner/privileged role only on the backend. No Supabase
project is linked, provisioned, or modified by this PR.

The seed inserts only the known synthetic study
`30f04fb1-10cd-5674-88a0-2a6b4962a848`. Inserts run in one transaction, concurrent
seeds take an advisory lock, and conflicts leave existing rows unchanged. It
never resets saved findings/reviews or deletes records. It sets v1 as the
approved baseline only for newly inserted artifacts; re-seeding never changes
an existing approved version. Protocol v2 is extracted/ready but unapproved.

The fixture has four artifacts, five versions, five fragments/facts, three
confirmed dependencies, one change, two findings, one synthetic membership,
and one audit event. Jobs start empty. Both version snapshots and the pinned
report edge remain available. The fixture is API-owned and provisional until
#21 aligns the shared IDs and uploadable source files. The seed actor is a
synthetic UUID, not a provisioned Supabase Auth account.

## Integrity and access

Composite foreign keys prevent version, fragment, fact, dependency, change,
and finding references from crossing studies/artifacts. Fact values are JSON
scalars. Added/removed changes have nullable before/after IDs. A version has
one pipeline job; retrying that job updates its row. Jobs have lease/retry
fields for #16; findings and changes have uniqueness guards for repeated
outputs. Claiming jobs and review-transition validation remain future tasks.

All 11 public tables have RLS enabled. Direct `PUBLIC`, `anon`, and
`authenticated` table privileges are revoked; no browser policies are introduced
in #14. #18 must add authenticated study access before public API exposure.
Membership UUIDs, audit actors, and optional finding owners are not tied to
`auth.users` yet. Resolution policy and path-edge validation belong to the
domain/review integration in #17 rather than this read adapter.

Reads use short repeatable-read, read-only transactions and explicit study
filters. SQL/connection failures return the sanitized 503 envelope
`{error:{code:"repository_unavailable",message:"Database reads are temporarily unavailable"}}`.
Unknown studies still return 404. `/health` is process liveness; database
readiness is verified through the study reads.

## Disposable local integration checks

PostgreSQL 15+ is required (`UNIQUE NULLS NOT DISTINCT`); validation used 17.11.
The following container is for local synthetic testing only:

```sh
docker run --name trialsync-postgres --rm -d \
  -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55414:5432 postgres:17
docker exec trialsync-postgres createdb -U postgres trialsync_test14
cd backend
TRIALSYNC_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55414/trialsync_test14 \
  .venv/bin/python -m unittest discover -s tests -v
docker stop trialsync-postgres
```

Wait until PostgreSQL is ready before `createdb`. Tests require an empty database
whose name begins with `trialsync_test`; they refuse to reset an existing schema.
Each run needs a new empty test database. Without the test URL, only fixture
tests run and database integration tests are explicitly skipped.

Checks cover migration application, fixture/API parity, a fresh adapter reading
persisted data, seed idempotence without review loss, study isolation, invalid
cross-study edges, nullable changes, job uniqueness, RLS, and revoked browser
grants. Hosted Supabase verification and shared #21 fixture integration remain
handoffs, not evidence supplied by the disposable PostgreSQL tests.
