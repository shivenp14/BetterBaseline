# Better Baseline assumption provenance

The methods are educational and conditional on the entered assumptions.
Provenance supports traceability; it does not validate those assumptions.

Provenance records where an input came from; it does not establish that the
assumption is clinically correct or that a hypothetical treatment works.
Binary endpoint risk concerns the eligible control population and a stated
follow-up period, not geographic disease prevalence.

## Origin labels

| API-v1 source tag | Meaning |
|---|---|
| `manual_user` | Explicitly entered by the user; no implied external verification |
| `synthetic_preset` | Hand-authored illustrative scenario, not clinical evidence |
| `protocol_curated` | Explicitly curated protocol input; preserve citation and description |
| `clinicaltrials_registry` | Public registry metadata; do not assume it states original design inputs |

The landed B1 `FieldProvenance` contains `source`, optional `description`,
`retrieved_at`, and `source_url`. `ExportPayload.provenance` is a field-keyed
dictionary. The landed B1 schema is the current transport authority. Schema
presence alone does not mean propagation through routes/exports is implemented.

## D1 fixture format

Each preset manifest contains `preset_id`, `preset_version`, `scenario_origin`,
`inputs_hash`, and a provenance list. Each list entry identifies a JSON-pointer
`field`, its `value`, `origin`, `source_url`, `source_location`,
`verified_by_user`, and explanatory `basis`. Null override and simulation seed/
replicate inputs have entries too. These records are an explicit fixture format,
not a drop-in API `FieldProvenance` dictionary.

All three shipped presets are `synthetic_preset`, have no clinical citation,
and are not user-verified. Reference expectations and mock-response numbers
remain labeled illustrative. A mock seed-42 simulation value is not an actual
seed-42 run. Measured engine reports must be kept distinct from those mocks.

The D1 input hash is `sha256:` plus SHA-256 of UTF-8 JSON with sorted keys and
compact separators. It verifies the input payload, not the clinical truth of
its assumptions. The API's route/version hash semantics must be documented
separately; do not relabel a D1 hash as an API computation cache key.

## Editing, propagation, and reproducible exports

An edited preset field should be tagged `manual_user` through the owning state/
provenance adapter. Preserve unchanged fields' origins; do not continue to call
an edited value a curated or verified source value. Avoid silently supplying
missing biological parameters from registry metadata.

The B1 export schema has `export_schema_version=1`, `model_version`, planned design,
explicit frozen enrollment, optional stress scenario, optional design/evaluation/
grid results, `software_versions`, `provenance`, and `exported_at`. Retain all
displayed result methods, warnings, input identity, and simulation seed/replicate
metadata. Actual random retained counts must not overwrite floored analytical
counts or planned enrollment.

Replay requires the exact inputs, fixed counts, effect parameterization,
alpha/target, dropout, seed/replicates, numerical method versions, software
versions, and generation command/commit. A timestamp records when computation
or export happened; it is not evidence of verification. Keep all values finite
and all probabilities as fractions in machine-readable artifacts.

## Remaining integration checks

B5 #67 owns normalization and propagation; final export assembly belongs to
#76. When those land, verify field keys/source mapping, preservation after edits,
method/hash behavior, and export replay against real outputs. D6 preparation
does not modify fixture manifests, schemas, routes, frontend state, or exports.

## D6 measured report identity

D6's reports preserve D1's original field ledger and fixture input hash. They
separately record a computation hash over workload, fixture inputs, numerical
method identity and explicit grid axes. The 31×21 axes are labeled synthetic
benchmark inputs; they are not added to D1's original provenance manifest.
Method identities are read from the actual analytical/simulation modules.

Each report includes the numerical-core commit, per-module and harness source
hashes, UTC capture time, environment, raw timings, seed/replicates when used,
and the hash of a real representative result. Replayed outputs must match that
result throughout measurement. These report hashes are local benchmark audit
identities, not B6 cache keys or export provenance propagation evidence. API cache behavior is recorded in the merged live reports below. Actual
frontend-export traceability remains with #76.


## D6 real HTTP report identity

The pre-#116 HTTP reports retain exact route request payloads and the unchanged
D1 fixture provenance ledger separately. They do not claim the ledger was sent
through the service or that an actual UI export preserves it. Route-provided
input hashes retain their original format: design currently returns a shortened
hash, while grid/evaluation return a `sha256:`-prefixed digest. The benchmark
records these values without relabeling them as cache keys.

Only generation timestamps are excluded from deterministic replay comparison;
actual timestamps are retained separately. Hashes, software/method identifiers,
seed/replicates, warnings and numerical values remain part of the semantic result
identity. Service source hashes and harness hashes identify the measured local
code. That capture predates #116. The current cache measurements below resolve the
cache boundary; UI-export traceability remains with #76.


## D6 merged cache and browser evidence

Current reports in scripts/benchmarks/reports/live retain the real route request
and response separately from their observed cache keys. The frontend calls the
shared API helper: UI-only preset identity is stripped, and evaluation field
provenance is mapped to the backend ledger. Cache keys, result input hashes and
fixture hashes have distinct meanings; none verifies clinical assumptions.

For every measured request, an isolated observer records actual cache reads and
writes while forwarding to the real cache. Cold resets and observation resets
are outside timing. Same-seed hits preserve the evaluation response's original
computed timestamp. Changed seed or replicates produce distinct keys/misses.
Grid requests have no cache activity and fresh timestamps. The design route
caches the solver result and reconstructs its response without a timestamp.

Current route keys include route, model version and normalized request defaults;
they do not separately identify software or numerical method versions. The
reports use fresh services, preserve software/source hashes, and make no claim
that an older cache entry is valid after a software change. Final UI export
assembly, field-source preservation in a downloaded export and replay of that
export remain the responsibility of #76.

New source hashes normalize UTF-8 CRLF/CR line endings to LF; historical raw
hashes remain capture metadata. Continuous numerical audits use bounded 1e-12
relative/absolute tolerance across environments. Discrete counts, masks, shapes
and seeds remain exact. The browser evidence includes a temporary benchmark-owned
31×21 page using the real shared API helper, alongside the production workspace.
