# Better Baseline frontend

The Next.js workspace uses the local FastAPI service for fresh design calculations
and stress evaluations by default. The versioned synthetic presets shown at startup
are fixtures: in live mode they are labeled as stale/demo data until an endpoint
returns successfully. The explicitly selected demo mode uses fixtures and local
analytic formulas and labels every result as demo output.

## Workspace pages

The workspace is split into `/plan`, `/stress-test`, `/simulation`, and
`/methods`; `/` redirects to `/plan`. Use the shared page navigation or the
next/back links to move between tasks. A persistent workspace provider keeps
draft inputs, request ownership, calculation snapshots, and simulation state
alive during client-side navigation. A direct URL or hard reload starts with
the default preset and gives a calculate-first recovery message on pages that
need a current enrollment lock.

Planning assumptions, the active stress scenario, export eligibility, and all
scientific/statistical outputs retain the existing API and provenance rules.
Range charts live under the advanced disclosure on Stress-test; provenance,
historical context, disclosures, and JSON export are grouped on Methods.

## Start locally

Requires Node.js 20.9+, npm, Python 3.12, and `uv`. From the repository root:

```bash
cd backend
uv sync --locked --extra dev
uv run --locked python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open <http://localhost:3000>. `.env.example` selects live mode and points to the
local service. To use fixture and client-computed output intentionally, set
`NEXT_PUBLIC_API_MODE=demo` in `.env.local` and restart Next.js. The service permits
the default localhost and 127.0.0.1 frontend origins through `ALLOWED_ORIGINS`.

## API and provenance boundary

`lib/contracts.ts` describes the backend numerical schema plus UI-only metadata.
The planning assumptions form validates the user's RR/ARR, baseline risk, alpha,
power, and symmetric dropout entries before calculation. Valid edits update the
workspace draft and per-field provenance immediately; only submitting
“Calculate & Lock Design” replaces the frozen enrollment with the calculated
counts. Recalculation invalidates pending evaluation/grid requests and rejects
their late responses.
`lib/api.ts` strips `preset_id` and sends the actual per-field ledger as the API's
`provenance` map for calculate, evaluate, and grid requests. The adapter places the
server-returned field records in `result.provenance.field_provenance`, preserving
source location, verification state, diagnostics, warnings, methods, and hashes.
Older responses without a provenance map fall back to the submitted ledger for
backward compatibility. Grid axes are mapped from frontend arrays to the backend
`{min, max, steps}` schema and returned points are normalized for the UI while
retaining canonical backend fields for JSON export.

After a stress slider or number field changes, the current evaluation is marked stale
and one evaluation is sent after 350 ms without another edit. The calculated enrollment
lock is included unchanged. Each request gets a distinct revision in addition to
best-effort abort cancellation, so a late response cannot replace a newer result.
"Download current results (JSON)" follows the backend `ExportPayload` shape, carries
the latest field provenance, and computes the canonical export-level `inputs_hash`
over assumptions, enrollment, stress scenario, and normalized provenance. It keeps
the full API responses nested, including their provenance, diagnostics, methods,
warnings, timestamps, and hashes, along with available software versions. It
includes only results whose status is current. Results that do not satisfy the
canonical response shape (such as demo-only grids or evaluations without Monte Carlo
output) and all mock/demo outputs are omitted rather than filled with fabricated
values.

The backend grid route is still the #66 scaffold and returns HTTP 501. Live mode
displays that service error instead of substituting client-side power calculations.
Demo mode retains preset grids and client-computed custom axes, including the complete
field provenance ledger on either result.

## Checks

```bash
npm run lint
npm run typecheck
npm run build
```

Run workspace invariants explicitly in demo mode after compiling the TypeScript test
entry point as CommonJS (the test uses the local TypeScript compiler):

```bash
./node_modules/.bin/tsc --strict --target ES2020 --module commonjs --moduleResolution node \
  --jsx react-jsx --esModuleInterop --skipLibCheck --rootDir . --outDir /private/tmp/bb-workspace-tests \
  tests/workspace-state.test.ts tests/stress-debounce.test.ts tests/workspace-export.test.ts \
  lib/api.ts lib/debounce.ts lib/workspace-export.ts lib/workspace-state.ts
NEXT_PUBLIC_API_MODE=demo node /private/tmp/bb-workspace-tests/tests/workspace-state.test.js
NEXT_PUBLIC_API_MODE=demo node /private/tmp/bb-workspace-tests/tests/stress-debounce.test.js
NEXT_PUBLIC_API_MODE=demo node /private/tmp/bb-workspace-tests/tests/workspace-export.test.js
```

Run adapter regressions and the real local service flow with:

```bash
npm run test:backend-integration
```

By default, that command installs the locked backend/dev dependencies, starts a
temporary Uvicorn service on a free localhost port, verifies calculate → freeze
enrollment → edit stress → evaluate and grid with provenance, checks the current
grid response shape, captures the actual downloaded export JSON, and validates it
against the backend `ExportPayload` model. It stops the temporary process on exit.
If a compatible Python 3.12 environment is already available, set
`BACKEND_PYTHON=/path/to/python` to use its installed dependencies without running
`uv sync`; the default locked `uv` path remains unchanged.

The interface remains semantic, unstyled HTML with native controls and tables. Keep
functional behavior, validation, loading/error/stale states, provenance, keyboard
access, and scientific warnings intact while visual design remains a separate task.
