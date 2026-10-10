# Worker pipeline (#16)

The separate worker requires the same durable `DATABASE_URL` and private storage
configuration as the API. It cannot process the API's default in-memory jobs.
Apply both migrations in filename order and seed before starting it. The worker
migration scopes change uniqueness by candidate version, including removals with
no after-fact ID. Existing seeded changes retain their legacy uniqueness. Install
the backend package to register `trialsync-worker`.

```sh
python -m pip install -e backend
trialsync-api
# In another terminal with the same DATABASE_URL / LOCAL_STORAGE_ROOT:
trialsync-worker --adapter demo
```

`demo` is an explicit synthetic-study-only adapter. It accepts a UTF-8 JSON
**complete snapshot**, not a PDF or office document:

```json
{"facts":[{"logical_key":"primary_endpoint_week","label":"Primary endpoint",
"value":36,"unit":"week","locator":"fixture:1","quote":"Endpoint week 36"}]}
```

For the seeded protocol, use the exact logical key/label/unit returned by the
approved baseline fact from `GET /api/studies/{study_id}/graph`. Upload the JSON
to `POST /api/artifacts/{protocol_id}/versions`, run
`trialsync-worker --adapter demo --once`, then poll `GET /api/jobs/{job_id}`.
Expected: `succeeded`/`complete`, version `ready`, a new candidate fact and change,
and findings on the confirmed/current downstream schedule and analysis facts.
Pinned report dependencies are excluded. Source text and explanations identify
these as synthetic fixture results. `{"facts":[]}` removes the approved facts;
an unseen logical key creates an added fact and a link-review finding. This stub
uses exact scalar/unit comparison, not the domain module's numeric normalization.

## Integration port

Select `--adapter package.module:factory` for a factory returning the
`app.worker.Pipeline` interface:

- `extract(content: bytes, context: Context) -> list[Fact]`
- `compare(facts: list[Fact], context: Context) -> list[Change]`
- `assess(changes: list[Change], facts: list[Fact], context: Context) -> list[Finding]`

Pydantic models or matching dictionaries are accepted. Context supplies the
version metadata, `previous_facts` from the artifact's **approved snapshot**,
the study's approved graph, artifact kinds, and approved-version IDs.
Extraction wrappers can pass these as `previous_facts` / `existing_facts` to
their modules. The wrapper for domain comparison passes previous and candidate
fact dictionaries to `compare_facts`; impact receives the changes, approved graph
plus candidate facts, dependencies, actual study ID, and artifact-kind lookup.
No ingestion/domain modules are vendored into this branch. #25 and #32 remain
live integration handoffs; the intermediate #30 adapter has empty explanation
and source output until #32 enrichment is supplied. There is no silent fallback
to fixture results if a live adapter fails.

The worker validates result scope, snapshot references/values, uniqueness,
confirmed/current edge paths, and open/unassigned findings before writing.
Candidate processing never approves a version, inserts an edge, changes an
existing finding's review state, or appends a user audit action. Read endpoints
currently include candidate/historical snapshots; review/projection selection
belongs to #17. Approved-version or graph changes during processing reject the result
and retry against fresh context.

## Claims, retries, and restart recovery

`FOR UPDATE SKIP LOCKED` claims one eligible job atomically. The existing unique
job-per-version constraint prevents duplicate enqueue. A new random ownership
token and increasing attempt number fence each claim. By default a lease lasts
120 seconds; it renews before extraction, comparison, assessment, and persistence.
Each individual step must finish inside that interval (or configure
`--lease-seconds` to suit the adapter's bounded timeout). There is no background
heartbeat extending a hung adapter indefinitely. An expired attempt cannot
renew, fail, or publish results, even if no replacement has claimed yet.

Adapter/storage/validation failures queue retries at 5 seconds times the attempt
number. `--retry-seconds` changes that delay. After `--max-attempts` (default 3),
the job and version become `failed`. Error polling shows the failing stage plus
a sanitized code; raw exception/document/credential text is never exposed.
Final-attempt crashes become `failed` with `lease_expired` on the next worker
claim. This automatic recovery does not need manual retry/reset controls (#20).

Facts, source fragments, changes, findings, version readiness, and success are
one transaction, with ownership checked before and after result writes. A crash
before commit leaves no partial output. A crash after commit leaves `succeeded`,
which is never claimed again. Deterministic demo IDs and unique fact/change/finding
constraints supplement the fenced transaction; retries do not overwrite reviews.
Storage is read privately with the 10 MiB upload bound and checked against SHA256.
Supabase downloads use the backend authenticated object endpoint, never a public
bucket URL; the hosted adapter is verified with mock HTTP contracts only.

Restart walkthrough: upload a fixture, start a worker with `--lease-seconds 10`,
and interrupt it while the job is `running`. Restart after that lease expires.
The job's attempts increment and it publishes one result set. To reproduce without
timing races, the integration tests claim a job, expire its lease in the disposable
database, reclaim it, and assert that the stale worker cannot complete or mutate
the job. They also inject a finding-write failure and a lease expiration during
result writes, verifying complete rollback.

## Verification

Against **three fresh disposable** databases named `trialsync_test*`:

```sh
TRIALSYNC_TEST_DATABASE_URL=postgresql://postgres@localhost:55416/trialsync_test_reads \
TRIALSYNC_UPLOAD_TEST_DATABASE_URL=postgresql://postgres@localhost:55416/trialsync_test_uploads \
TRIALSYNC_WORKER_TEST_DATABASE_URL=postgresql://postgres@localhost:55416/trialsync_test_worker \
backend/.venv/bin/python -m unittest discover -s backend/tests -v
```

Tests refuse existing databases and never reset user data. Without these settings,
database suites are explicitly skipped. No hosted database, credential, auth,
deployment, or worker autoscaling is configured by this issue.
