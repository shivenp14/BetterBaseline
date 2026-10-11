# #75 isolated simulation panel handoff

This completes the isolated #75 component and shared #72 API integration.
#76 owns production page/state/export assembly. Only
MonteCarloPanel.tsx, MethodDisclosures.tsx, simulation-client.ts and
monte-carlo.* tests are delivered. Shared page/API/contracts/package files are
unchanged. The panel is unstyled semantic HTML.

## Interface and completed handoff

`MonteCarloPanel` takes an immutable `SimulationSelection` (planned design,
frozen enrollment, exact selected baseline/dropout/effect, optional field
provenance), an injected `runSimulation(request, signal)`, optional
`unavailableReason`, and optional `onResult(result, request)`. Only the current
successful run reaches onResult, allowing parent export state to retain the
complete validated result. Keep the adapter reference stable across equivalent
parent rerenders. Pass a null selection or unavailable reason whenever the
parent's design/selection is stale, missing or invalid.

`createSimulationClient(transport)` validates the runtime backend response and
checks cancellation before/after transport. `createSharedSimulationTransport()`
uses the unchanged #72 `evaluateScenario` helper. `runSelectedSimulation` is a
stable module-level validated adapter for the #76 parent to pass as runSimulation.

The adapter translates selection `provenance` into `provenance_ledger` for the
shared helper, which sends the backend's `provenance` field and strips UI-only
`preset_id`. Its response envelope's `provenance.field_provenance` is normalized
back into the panel's field ledger. Both MCSEs, warnings, count aggregates,
RNG/software versions, timestamps and input hash are preserved and checked.
Shared EvaluateResponse types do not yet declare all live backend metadata;
#75 checks those fields at runtime rather than editing shared contracts or
inventing missing data. The temporary independent HTTP transport is removed.

Live simulation requires `mock: false` and execution mode `backend`. Explicit
demo mode is rejected with an unavailable message; no demo result is presented
as a live run. Missing simulation, malformed or mismatched metadata, server
limits and connection failures remain visible errors. The app defaults to live
mode; NEXT_PUBLIC_API_BASE_URL configures the shared helper's backend URL.
Selection/options identity includes both effects, frozen N, dropout, alpha,
target, seed, replicates and field sources. #76 passes null selection or an
unavailable reason for a stale or missing planned design and retains only the
current onResult callback for export. No #76 production wiring is included.

## Behavior

Seed/replicate defaults are 42/10,000. Bounds match merged #65: seed
0..2^32-1, replicates 1..100,000, equal enrollment at most 1,000,000 per arm.
Explicit Run submits one selected scenario. Edits immediately mark an existing
result stale and invalidate/abort active work. A monotonic generation counter
also rejects late responses from adapters that ignore cancellation. Unmount
aborts work; obsolete results never notify the parent. Requests cannot duplicate
while active, and an aborted identity can be selected and run again.

Two-sided and favorable fractions and MCSEs have separate labels. MCSE display
uses percentage points. Expected analytical counts, frozen enrollment and mean
actual retained/event counts are distinct. Null fixtures explain alpha versus
alpha/2; simulations are synthetic/conditional and do not predict efficacy.

## Reproduction

From frontend/ with installed existing dependencies:

```sh
./node_modules/.bin/tsc lib/simulation-client.ts components/MonteCarloPanel.tsx components/MethodDisclosures.tsx --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --outDir /private/tmp/c6-render
C6_RENDER_ROOT=/private/tmp/c6-render NODE_PATH="$PWD/node_modules" node --test tests/monte-carlo.test.mjs
npm run typecheck
npm run lint
npm run build
```

In a disposable checkout, serve the real backend on 127.0.0.1:8000. Add a
temporary app/c6-harness/page.tsx containing:

```tsx
export { default } from "../../tests/monte-carlo.harness";
```

Run the frontend on localhost:3000 (the default permitted Next dev origin). Install Playwright/Chromium separately
without changing manifests and run:

```sh
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/c6-browsers C6_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/monte-carlo.browser.mjs
```

Remove the temporary page before the production build. The browser harness
uses fresh real backend responses, including its explicit delayed adapter that
ignores cancellation. Fixture objects are used only in the standalone unit and
server-render suite. Browser checks cover a fresh 10k seeded response, native
keyboard controls and bounds, one call per run, pending duplicate rejection,
out-of-order completion, effect/selection changes, failure/invalid/unavailable
states, and unmount abort. Acceptance additionally verifies the actual HTTP payload has the field ledger,
seed/replicates and no UI-only keys, and that returned field provenance is visible.
Production page assembly and downloaded-export acceptance remain with #76.

Validated: 11 unit/render tests, real shared-helper browser checks, lint,
typecheck and a clean production build. Temporary acceptance wiring and generated
Next files are excluded from the PR.
