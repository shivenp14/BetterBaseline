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
Outputs sort by that identity and use UUIDv5 IDs derived from the complete
change payload, including snapshot references. Retries and input reordering
therefore preserve IDs; distinct amendment snapshots produce distinct IDs.

Finite numeric JSON values and strings containing only decimal/scientific
numbers compare exactly through Decimal, without floating-point tolerances.
Booleans stay distinct from numbers. Prose strings compare exactly. Unit outer
whitespace is ignored and null/empty units are equivalent; case, aliases, and
unit conversions are deliberately not inferred. A unit-only change is modified;
the caller can retrieve its units through the before/after fact references.
Labels and source formatting do not trigger changes.

Duplicate artifact/logical keys, missing required comparison fields, nonscalar
values, and nonfinite numbers raise ValueError. Supply one snapshot per logical
identity on each side. This module does not approve versions or propagate impact.
