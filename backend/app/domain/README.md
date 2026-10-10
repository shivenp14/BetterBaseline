# Fact comparison (task #29)

No dependencies or backend scaffold are required. From the repository root:

```sh
PYTHONPATH=backend python3 -B -m unittest discover -s backend/app/domain -v
```

The API/worker can import `compare_facts` from `app.domain` when `backend` is on
the Python path. Pass iterables of Fact dictionaries from the shared contract
in issue #4; the return value is a list of Change dictionaries for persistence.

For a manual walkthrough, compare an endpoint fact with value `24`, unit `week`
against its replacement with the same artifact/logical key and value `36`.
One `modified` change contains both snapshot IDs and the original values.
Changing `24` to `"24.00"` produces no change. An absent old/new fact produces
`added`/`removed` with a null before/after reference respectively. Explicit null
values remain distinguishable from absent facts by those references and kind.

Facts match by `(artifact_id, logical_key)`; IDs identify version snapshots.
Outputs sort by that identity and use UUIDv5 IDs derived from artifact ID,
logical key, change kind, and normalized before/after values and units.
Regenerated fact IDs and numeric formatting do not change the change ID;
snapshot references in the output still point to the supplied extractions.
Task #31 additionally scopes identity by before/after version_id. Supply stable,
nonempty version IDs from persistence: retries of the same version pair share
an ID; later amendments with the same logical transition receive distinct IDs.

Finite numeric JSON values and strings containing only decimal/scientific
numbers compare exactly through Decimal, without floating-point tolerances.
Booleans stay distinct from numbers. Prose strings compare exactly. Unit outer
whitespace is ignored; null and empty units remain distinct. Case, aliases, and
unit conversions are deliberately not inferred. A unit-only change is modified;
the output preserves original units as additive `before_unit`/`after_unit`
fields, with null for an absent side. Consumers of the original #4 Change
schema must allow these fields or adapt them explicitly before persistence.
Labels and source formatting do not trigger changes.

Duplicate artifact/logical keys, missing required comparison fields, nonscalar
values, and nonfinite numbers raise ValueError. Supply one snapshot per logical
identity on each side. This module does not approve versions or propagate impact.

# Dependency traversal (task #30)

Import `assess_impact` from `app.domain`. Pass changes from `compare_facts`,
the old fact snapshots plus dependent snapshots, and the prior approved graph:

```python
findings = assess_impact(changes, facts, dependencies, study_id=study_id)
```

The three positional arguments remain compatible with the shared interface.
`study_id` is optional worker context because the shared Fact/Change records
do not contain it. Without that context the output study_id is null; supply
the actual study ID before persistence. Fact snapshots and graph records must
belong to that study. The caller must select the active approved graph, rather
than mixing every historical edge still marked `current`.

Modified and removed changes start at `before_fact_id`, following upstream to
dependent through confirmed/current edges only. Pinned and proposed edges are
excluded, including their branches. A visited set per change handles cycles,
self-loops, and converging paths. Breadth-first traversal with edges sorted by
ID retains one deterministic shortest edge path; this is not an impact score.
The changed root itself is excluded even if a cycle leads back to it.

Findings deduplicate by `(change_id, affected_fact_id)` and use UUIDv5 IDs
derived from study context and that pair. Input order, repeated identical records, and alternate
paths do not change finding identity. Conflicting duplicate IDs and missing
confirmed/current endpoints raise ValueError instead of silently losing work.

Added facts produce one finding on the new fact with an empty edge path. This
means link review is required, and does not infer downstream dependencies.
No candidate graph is traversed for added facts. For this traversal slice,
action defaults to `review_document`, explanation is empty, and sources are
empty. Artifact context enables typed actions as described below; evidence
explanations follow in #32. No versions, edges, or existing findings are mutated.

Manual walkthrough: compare protocol endpoint week 24 against week 36; supply
protocol-v1 → schedule → analysis confirmed/current edges and a pinned edge to
report. The output contains schedule and analysis findings with their edge
paths, and no report finding. Add analysis → protocol-v1 to verify the cycle
terminates without duplicating findings. These scenarios run in test_impact.py
alongside compare_facts with the same unittest command above.

# Impact actions (task #31)

Provide optional `artifact_lookup`, a mapping keyed by artifact ID with values
such as `{"kind": "analysis_result"}` or the explicit kind string itself:

```python
findings = assess_impact(
    changes, facts, dependencies, study_id=study_id,
    artifact_lookup={
        schedule_artifact_id: {"kind": "visit_schedule"},
        result_artifact_id: {"kind": "analysis_result"},
        report_artifact_id: {"kind": "report"},
    },
)
```

| Dependent kind | Final relationship | Requested action |
| --- | --- | --- |
| document, protocol, analysis_plan, visit_schedule, report | defines, describes, calculated_from, requires, covered_by | review_document |
| analysis_result | defines, calculated_from, requires | rerun_analysis |
| Unknown/missing kind or unsupported relationship | Any | review_document |
| Added fact with no retained dependency path | None | review_document (link review) |

These are explicit adapter kind names: the shared contract does not define an
Artifact kind enum. The API/ingestion adapter must map its names to these values;
filenames and labels are never used to guess a kind. An analysis plan is a
document; an analysis result is a computed output. A report downstream of a
result receives document review, even if an earlier edge requests reanalysis.

Selection considers every eligible incoming edge reached during traversal.
If any supported relationship requests rerun_analysis, it takes precedence
over review_document. The finding retains a supporting path for the selected
action, choosing shortest length then edge-ID order among equal actions.
Nodes are expanded once, cycles and self-loops are excluded from supporting
paths, and changing the selected path does not duplicate downstream findings. Unsupported edges still
participate in traversal and produce a review fallback, rather than losing
findings. Omitting the lookup preserves the existing three-argument behavior.

Actions do not affect finding IDs, paths, status, or resolution. `rerun_analysis`
requests a rerun for review; it does not execute analysis or approve an output.
Pinned/proposed edges remain excluded. Sources and explanations stay reserved
for #32, and participant-support rules remain reserved for #35.
