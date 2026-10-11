# Better Baseline frontend shell

An isolated, offline-first Next.js shell for the Better Baseline trial planning demo.
All displayed figures come from local synthetic fixtures. The frontend does not
implement statistical formulas and does not contact a backend or any external service.
The interface is raw semantic HTML with native controls and no styling; appearance is
left for a later pass.

## Start locally

Requires Node.js 20.9+ and npm.

```bash
npm ci
npm run dev
```

Open <http://localhost:3000>. The shell runs without network access after dependencies
are installed. To check the production bundle:

```bash
npm run lint
npm run typecheck
npm run build
npm start
```

## Mock contract boundary

`lib/contracts.ts` defines request and response types for `calculate`, `evaluate`, and
`grid`, including the backend's snake_case fields and provenance metadata. `lib/api.ts`
is an in-process mock adapter over `lib/mocks.ts`; it does not use `fetch`. Responses
are fixed illustrative snapshots, not calculations. Inputs can be changed to exercise
the request boundary, but results remain fixture values. The planned enrollment remains
fixed when the stress scenario changes.

The heatmap is laid out as `[dropout][baseline]`. Its values and 80% frontier are
illustrative. Invalid scenarios are represented as `null` with a matching
`invalid_mask` entry. Simulation fields use the canonical pooled two-proportion
z-test names, seed, replicate count, MCSE, and invalid-test fraction; values are mock
examples and are not a run of Monte Carlo simulation.
