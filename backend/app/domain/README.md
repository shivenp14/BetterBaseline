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
