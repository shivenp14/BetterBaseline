# Review API (#17)

`PATCH /api/dependencies/{id}` accepts `{"status":"confirmed"}` and returns
the dependency. Confirmation requires same-study endpoints, retained source
evidence, and distinct endpoint IDs. Current edges must reference approved
snapshots; pinned edges can keep historical snapshots. Already-confirmed valid
requests are idempotent and do not append another audit event.

`PATCH /api/findings/{id}` accepts any nonempty subset of
`{status,owner_id,resolution}` and returns the updated finding. Omitted fields
retain their values; explicit `owner_id:null` clears assignment. Owners must be
study members. No client `actor_id` is accepted.

```json
{"status":"resolved","resolution":{"decision":"no_change",
"note":"Reviewed the source and retained this interpretation.","replacement_version_id":null}}
```

Local validation pending domain #33 integration:

- `open` can remain open, enter review, or close with valid evidence.
- `in_review` can remain in review or close; it cannot return to open.
- `resolved` and `dismissed` are terminal and immutable, with identical retries
  accepted. No reopen flow is added.
- Closure requires a nonblank note, up to 2000 characters. `no_change` records
  justification and has no replacement. Dismissal uses `no_change`.
- `updated` resolves with a ready, newer version of the affected artifact in the
  same study. If the replacement has a job, it must have succeeded. The affected
  snapshot itself or an older version is not replacement evidence.
- `reanalysis_requested` requires a note and stays `in_review` with no replacement.
  Requesting an analysis does not prove it was completed. A later close must
  supply new valid `updated` or `no_change` evidence.

Invalid input returns 422 (`invalid_review`/`invalid_request`); conflicting closed
states, approval rollback, or unmappable current links return 409
(`review_conflict`). Unknown records return 404. Access denial returns 403.

## Explicit version approval and graph projection

`POST /api/versions/{id}/approve` is an additive review endpoint returning the
ready ArtifactVersion. Use it to approve an upstream protocol revision without
pretending to resolve its downstream findings. An `updated` finding resolution
also approves its valid replacement **in the same transaction**.

The local projection maps the existing approved graph's confirmed/current edges
by artifact-scoped logical key onto the replacement version. Rebound edges get
new deterministic IDs. Old facts, fragments, versions, edges, evidence, and
findings remain queryable. Pinned and proposed edges stay fixed; approval never
confirms proposed extraction links. If a linked fact is missing, approval returns
409 and rolls back rather than silently losing a downstream dependency. Database
fact-key uniqueness prevents ambiguous target mappings.

Already-approved versions are idempotent. Approval cannot roll back to an older
version. Only explicit approval changes `approved_version_id`; uploaded/processed
candidates remain unapproved until reviewed. Unrelated findings remain open.
`GET /graph` retains candidate/historical snapshots; the worker selects approved
facts/edges for propagation. UI history/projection presentation is a handoff.

## Transactions, actor, and integration hooks

Database review calls serialize against the study's artifact rows, then lock the
target dependency/finding. Mutation, projection, approval, and actor audit events
are one transaction. Audit failures roll everything back. Identical retries make
no additional changes or events. Actions are `dependency.confirmed`,
`finding.updated`, and `version.approved`; the existing audit schema records actor,
entity, study, and UTC timestamp. It does not contain before/after payloads.

Until #18, the server selects the seeded demo actor
`f0e3b7e5-deb8-5441-b668-c7acfb4daab2`; API remains localhost-only. PostgreSQL
requires actor/owner membership in the study. In-memory membership uses fixture
audit actors and is intentionally not durable across process restarts.

`app.api.reviews.get_review_actor` is a request dependency for #18 to replace
with the authenticated user. Existing `get_study_access` runs before each write.
`create_app(review_actor=..., review_policy=...)` supports local tests/adapters.
The `ReviewPolicy` port supplies `finding(current, patch) -> Finding` and
`projection(graph, approved_versions, replacement_version) -> list[Dependency]`.
Domain #33/#34 wrappers can replace `LocalReviewPolicy` without owning persistence.
Wrappers should raise `InvalidReview`/`ReviewConflict` for rejected outcomes.
Persistence always retains historical rows and owns approval/audit transactions.
No domain code was copied into this branch.

## Local walkthrough and checks

Use PostgreSQL and private storage configuration from the upload/worker notes;
apply the existing two migrations and `trialsync-seed`. No new migration is
required by #17. Start `trialsync-api` and `trialsync-worker --adapter demo`.

1. Upload a complete synthetic protocol JSON snapshot with endpoint week 36.
2. Wait for `succeeded`; record its two source-backed downstream findings.
3. Explicitly approve that version. Historical/pinned report links remain fixed,
   current schedule/analysis edges project onto the approved week-36 fact.
4. Resolve one finding with justified `no_change`. Restart the API and confirm
   its status/note and actor audit event persist; the other finding remains open.
5. Upload endpoint week 48 and run the worker. Comparison uses approved week 36,
   and both active downstream dependents remain reachable. Old findings are kept.

The complete suite uses four **fresh disposable** `trialsync_test*` databases:
`TRIALSYNC_TEST_DATABASE_URL`, `TRIALSYNC_UPLOAD_TEST_DATABASE_URL`,
`TRIALSYNC_WORKER_TEST_DATABASE_URL`, `TRIALSYNC_REVIEW_TEST_DATABASE_URL`.
Run `backend/.venv/bin/python -m unittest discover -s backend/tests -v` with these
variables set. Tests refuse existing databases and do not reset user data. Checks
include durable fresh-adapter reads, invalid resolutions, actor/owner membership,
access denial, concurrent/idempotent review, evidence confirmation, pinned/history
preservation, missing projection targets, and injected audit-write rollback.

Live authentication/hosted Supabase and domain #33/#34 policy integration remain
handoffs; this issue adds no notifications, editor, or user-management screen.
