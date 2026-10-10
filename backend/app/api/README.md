# Local fixture API (#13)

From the repository root:

```sh
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[test]'
backend/.venv/bin/trialsync-api
```

The server binds **127.0.0.1:8000**. This is an unauthenticated synthetic demo;
keep it on localhost until #18 provides auth and study access checks. The local
UI at `http://localhost:3000` or `http://127.0.0.1:3000` can read it via CORS.
OpenAPI and interactive documentation are at `/openapi.json` and `/docs`.
Set backend-only `DATABASE_URL` to use PostgreSQL reads after applying #14's
baseline migration and seed; see `app/persistence/README.md`. With no connection
string, fixture mode remains available.

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/studies
curl http://127.0.0.1:8000/api/studies/30f04fb1-10cd-5674-88a0-2a6b4962a848/graph
cd backend
python -m unittest discover -s tests -v
```

With the dependencies already installed, `cd backend && python -m app.main`
also starts the API. Python 3.11+ is required.

## HTTP handoff

`GET /health` returns `{status:"ok"}`. All study routes are under `/api`:

| Route | Response |
| --- | --- |
| `/studies` | `{items: Study[]}` |
| `/studies/{study_id}/artifacts` | `{items: Artifact[]}` |
| `/studies/{study_id}/graph` | `{facts: Fact[], dependencies: Dependency[]}` |
| `/studies/{study_id}/findings` | `{items: Finding[]}` |
| `/studies/{study_id}/audit` | `{items: AuditEvent[]}` |

Models live in `app.api.models`; field names for versions, facts, dependencies,
changes, and findings follow #2. The previously unspecified read shapes are
`Study={id,name}`, `Artifact={id,study_id,name,kind,versions:ArtifactVersion[]}`,
and `AuditEvent={id,study_id,actor_id,action,entity_id,created_at}`. Timestamps
serialize in UTC and IDs serialize as UUID strings. Unknown studies return 404
`{error:{code:"study_not_found",message:"Study not found"}}`; invalid IDs return
422 `invalid_request`. Framework 404/405 responses use the same error envelope.

## Adapter and collaborator imports

`app.persistence.repository.ReadRepository` defines synchronous
`list_studies()`, `list_artifacts(study_id)`, `get_graph(study_id)`,
`list_findings(study_id)`, and `list_audit(study_id)`. Study arguments are UUIDs.
Adapters return model objects and raise `StudyNotFound` for missing studies.
FastAPI runs these synchronous routes in its thread pool. #14 can supply a
database adapter through `app.main.create_app(repository=adapter)`; routes
do not depend on the in-memory implementation. Tests and callers can also use
`app.api.routes.get_repository` as the FastAPI dependency override point.

The shared manifest is `backend/pyproject.toml`; ingestion and domain owners can
add modules under `app.ingestion` and `app.domain` respectively. Their function
contracts remain the dictionary interfaces in #2; no worker is introduced here.
Coordinate dependency additions in the shared manifest with the API owner.

## Fixture walkthrough

`app.persistence/fixtures.json` is a temporary API-owned fixture pending #21's
shared demo handoff. It contains one study, four artifacts, five fact snapshots,
three confirmed edges, one change, two open findings, and a synthetic audit event.
IDs are deterministic UUIDv5 values derived from the URL namespace and
`https://trialsync.local/fixture/<key>`; the study key is `study`.

Protocol v1 says week 24 and v2 says week 36. Both versions and facts remain
visible. Current confirmed edges still originate from the v1 fact pending human
review/rebinding. Analysis-plan and visit-schedule findings request review; the
pinned historical report retains week 24 and has no finding. A `ready` extraction
status does not approve the replacement version or rebind graph edges. Findings
are canned demonstration outputs, not results from a running worker or engine.
The stored change is used for fixture consistency; #13 does not add a changes
endpoint beyond the agreed HTTP contract.

#14's scaffold prerequisite is supplied by this PR; its live seed integration
still needs coordination with #21. #18 continues to depend on #15 and #17.
Uploads, jobs, review mutations, storage, database, auth, and hosted deployment
remain separate tasks.
