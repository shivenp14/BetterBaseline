# Better Baseline frontend

The Next.js workspace uses the local FastAPI service for fresh design calculations
and stress evaluations by default. The versioned synthetic presets shown at startup
are fixtures: in live mode they are labeled as stale/demo data until an endpoint
returns successfully. The explicitly selected demo mode uses fixtures and local
analytic formulas and labels every result as demo output.

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
`lib/api.ts` strips `preset_id` and the local `provenance_ledger` from calculate
requests. Evaluate requests carry the ledger in the backend's accepted top-level
`provenance` map; the adapter maps that returned map into
`result.provenance.field_provenance`. Calculate responses have no backend provenance,
so the adapter adds the request ledger for workspace and export consumers and marks
the result as backend-executed. Grid axes are mapped from the frontend arrays to the
backend `{min, max, steps}` schema and returned points are normalized to the UI shape.

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
  tests/workspace-state.test.ts lib/api.ts lib/workspace-state.ts
NEXT_PUBLIC_API_MODE=demo node /private/tmp/bb-workspace-tests/tests/workspace-state.test.js
```

Run adapter regressions and the real local service flow with:

```bash
npm run test:backend-integration
```

That command installs the locked backend/dev dependencies, starts a temporary
Uvicorn service on a free localhost port, verifies calculate → freeze enrollment →
edit stress → evaluate with seeded Monte Carlo and provenance, checks adapter payloads,
and stops the temporary process on exit. It does not implement or claim a working
backend grid calculation.

The interface remains semantic, unstyled HTML with native controls and tables. Keep
functional behavior, validation, loading/error/stale states, provenance, keyboard
access, and scientific warnings intact while visual design remains a separate task.
