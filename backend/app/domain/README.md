# Fact comparison (task #29)

No dependencies or backend scaffold are required. From the repository root:

```sh
python3 -m unittest discover -s backend/app/domain -v
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
Repeated identical logical transitions share an ID, so persistence must scope
occurrences to the version/job when retaining separate amendment history.

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
derived from that pair. Input order, repeated identical records, and alternate
paths do not change finding identity. Conflicting duplicate IDs and missing
confirmed/current endpoints raise ValueError instead of silently losing work.

Added facts produce one finding on the new fact with an empty edge path. This
means link review is required, and does not infer downstream dependencies.
No candidate graph is traversed for added facts. For this traversal slice,
action is the conservative `review_document` fallback, explanation is empty,
and sources are empty. Typed actions (#31) and evidence explanations (#32)
will enrich these findings. No versions, edges, or existing findings are mutated.

Manual walkthrough: compare protocol endpoint week 24 against week 36; supply
protocol-v1 → schedule → analysis confirmed/current edges and a pinned edge to
report. The output contains schedule and analysis findings with their edge
paths, and no report finding. Add analysis → protocol-v1 to verify the cycle
terminates without duplicating findings. These scenarios run in test_impact.py
alongside compare_facts with the same unittest command above.
