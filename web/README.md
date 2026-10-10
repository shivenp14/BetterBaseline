# TrialSync web workspace

Issue #5: a Next.js 16 / React 19 / TypeScript study shell. Requires Node.js 20.9 or later and npm. All data is synthetic.

```sh
cd web
npm ci
npm run dev
```

Open http://localhost:3000. Fixture mode is the default and needs no backend, credentials, or network requests for study data. The seeded MERIDIAN workspace shows **4 artifacts**, **2 findings**, and **2 needing attention**. The protocol retains versions 1 and 2. The analysis plan and visit schedule have findings; the historical report has none.

## Fixture/live switch

Copy `.env.example` to `.env.local`. To use a backend:

```dotenv
NEXT_PUBLIC_API_MODE=live
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

Restart the development server after environment changes; production `NEXT_PUBLIC_*` values are set at build time, so rebuild when switching. The badge identifies the configured data source. Live errors appear with a retry button and do not silently fall back to fixtures. No authentication is implemented in this slice; the live backend must allow the browser origin through CORS.

`src/lib/api/client.ts` exposes the same `StudyApi` interface for both modes:

- `GET /studies` → `{items: Study[]}`
- `GET /studies/{id}/artifacts` → `{items: Artifact[]}`
- `GET /studies/{id}/findings` → `{items: Finding[]}`

The API base URL includes `/api`. Shared domain field names/enums follow [issue #1](https://github.com/shivenp14/TrialSync/issues/1), including nullable before/after fact IDs on changes. That contract does not define study/artifact list item fields: this shell provisionally uses `Study={id,name,description?}` and `Artifact={id,study_id,name,kind,versions:ArtifactVersion[]}`. Confirm these two summary shapes with the API owner during live integration. The adapter checks the list envelope; TypeScript types describe the expected item shapes, not runtime schema validation. Fixtures are small in-memory records cloned per request; they are not a complete dependency graph.

## Validation and walkthrough

```sh
npm run lint
npm run typecheck
npm test
npm run build
npm start
```

1. Open the workspace with no `.env.local` and verify the fixture badge and 4 / 2 / 2 counts.
2. Check the four artifact rows and two finding summaries. Historical report has no finding.
3. Resize to a phone viewport; panels stack and the study selector remains usable.
4. For failure handling, set live mode to an unavailable backend; verify the error and retry button. An API returning `{items:[]}` from `/studies` shows the no-studies state; empty artifact/finding lists have their own messages.

Tests cover fixture isolation/history, unknown studies, live routes, shared error envelopes, malformed responses, network errors, and mode configuration. Graph layout, uploads, authentication, and review actions belong to subsequent issues.

Development dependency audit: npm reports a high-severity `braces` advisory through Next.js ESLint tooling. The latest published `braces` release is still affected, and npm's suggested remediation downgrades the Next.js lint configuration across major versions. Production dependencies pass `npm audit --omit=dev` with zero vulnerabilities; revisit the development advisory when an upstream patch is available.
