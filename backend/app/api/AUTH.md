# Authentication and study access (#18)

The API defaults to `TRIALSYNC_AUTH_MODE=required`. Every `/api` request requires
one `Authorization: Bearer <Supabase user access token>` header. Missing,
malformed, duplicate, expired, or invalid credentials return 401 with
`WWW-Authenticate: Bearer`. The verifier runs before multipart parsing; nonmember
uploads also reject before reading their bodies. `/health`, OpenAPI and API docs
contain no study data and remain public. Browser CORS preflight is handled without
a bearer token; it does not authorize the subsequent request.

## Configuration

Use backend/.env.example as the configuration reference (the application reads
environment variables; it does not load that file automatically):

```text
TRIALSYNC_AUTH_MODE=required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
DATABASE_URL=<backend-only PostgreSQL DSN>
CORS_ORIGINS=https://your-web-origin.example
```

Use a project **publishable** key for identity verification, not an elevated
service-role/secret key. There is no JWT-secret configuration or `getSession`
identity shortcut. Supabase URL alone no longer selects remote storage; add both
backend-only `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_STORAGE_BUCKET` for the
existing private-storage adapter. That adapter still uses its legacy backend
service-role key; migration to secret API keys is a separate storage handoff.
Keep database and elevated storage credentials out of frontend configuration.

Verification calls the configured project's HTTPS `GET /auth/v1/user` with the
publishable `apikey` and user's bearer token. The Auth server validates the token;
the API accepts only a valid UUID from an authenticated user response. It never
decodes an unverified token for identity or uses editable `user_metadata` for
authorization. No user identity/token cache is added. Network/server failures
return a sanitized 503, never demo access or raw response/credential text. The
network timeout is five seconds. Responses are checked once per request, before
route dependencies run. Session/token lifetime remains controlled by Supabase;
this API does not add session-revocation administration.

The implementation follows the current [Supabase JWT verification
guide](https://supabase.com/docs/guides/auth/jwts) and [API key migration
guide](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys).
No Supabase Python package or cryptography dependency is required for remote
verification; the existing pinned HTTP client is used.

Missing publishable-key configuration keeps the API locked: missing credentials
return 401, attempted verification returns 503. Invalid URL/key configuration
rejects startup. API-key strings cannot be used as user bearer tokens. A valid
token from another project is rejected by the configured Auth server.

## Membership and actor

`GET /api/studies` queries only studies with a current memberships row for the
verified UUID. All study reads check membership; artifact uploads, job polling,
version signing/approval, dependency confirmation, and finding updates resolve
their record's study and check it. Nonmembers return 403. Database membership is
checked on each request, so removing it denies subsequent requests even with a
still-valid bearer token. No JWT profile/role claim grants study membership.

The existing demo seed's fixed actor UUID is synthetic; it is not an Auth user
provisioning system. Before using a hosted Auth account, an operator must associate
that account's verified UUID with the demo study in the existing memberships table
through their private database tooling. No invitations, role administration,
signup UI, or automatic membership grant is added. Browser database grants remain
revoked with RLS enabled; the API/worker use backend credentials and enforce the
API checks. Authenticated users do not gain direct Data API access to the tables.

Audit writes derive `actor_id` from the request's verified UUID, ignoring the old
demo actor setting. A caller-supplied actor field is rejected by the review request
contract. Repository review transactions also check the actor's membership and
validate assigned owners. Tests can inject a `TokenVerifier` through
`create_app(token_verifier=...)`; no environment option selects a fixture verifier.

## Private source URLs and browser calls

`GET /api/versions/{id}/source` requires token and membership **before signing**
and responds with `Cache-Control: private, no-store`. Local signed downloads also
require a bearer token and current membership for the exact persisted storage path,
as well as a valid expiry/signature; orphan objects are not downloadable through
the API. Fetch both the source endpoint and the returned local URL with the bearer
header, then display/download the fetched blob. A plain browser navigation cannot
attach that header.

Hosted Supabase signed URLs are short-lived bearer capabilities (existing TTL 60
seconds). They can be downloaded without a separate user header once issued; do
not share them. Membership gates issuance, while an already-issued hosted link
remains usable until its TTL expires. The API does not claim immediate revocation
of an issued Supabase capability.

`CORS_ORIGINS` accepts exact comma-separated HTTP(S) origins, without wildcards,
credentials or paths. Local defaults are localhost/127.0.0.1 port 3000. Methods
GET/POST/PATCH and headers Authorization/Accept/Content-Type are permitted.
Credentials/cookies are not enabled. CORS is a browser policy; the token and
membership checks also protect nonbrowser clients.

## Local synthetic mode and verification

For an intentional localhost rehearsal with no Auth project:

```sh
TRIALSYNC_AUTH_MODE=demo trialsync-api
```

The CLI continues binding to 127.0.0.1. Demo mode restores the synthetic policy
and fixed demo actor; use required mode before public exposure. Prior synthetic
tests now explicitly select demo mode through trialsync_test_support.demo_app;
the production default is never implicitly bypassed because a repository is
injected. Existing upload/worker/review walkthroughs require this explicit setting
if no hosted Auth project is configured. The worker is a privileged backend
process and does not need user bearer tokens.

The full suite uses five **fresh disposable** `trialsync_test*` databases:
TRIALSYNC_TEST_DATABASE_URL, TRIALSYNC_UPLOAD_TEST_DATABASE_URL,
TRIALSYNC_WORKER_TEST_DATABASE_URL, TRIALSYNC_REVIEW_TEST_DATABASE_URL,
TRIALSYNC_AUTH_TEST_DATABASE_URL. Run
`backend/.venv/bin/python -m unittest discover -s backend/tests -v` with all five
set. Tests refuse existing databases and never reset user data.

Auth checks cover missing/malformed/duplicate credentials, Auth HTTP rejection
and outages, privileged API keys, ignored editable metadata, member-filtered
studies, every read/write route, pre-spooling upload denial, job/source access,
local signed-download membership removal, derived audit actor, and exact CORS.
PostgreSQL tests exercise real membership rows, scoping, revocation, private
uploads and actor audit with a fixture identity verifier. Supabase verification
HTTP contracts are mocked; hosted sign-in requires configured project credentials
and an actual member account and remains a deployment verification handoff.
