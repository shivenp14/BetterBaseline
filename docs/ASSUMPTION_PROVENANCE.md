# Better Baseline assumption provenance

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
identities, not B6 cache keys or export provenance propagation evidence. API
cache identity and actual frontend-export traceability remain integration gates.
