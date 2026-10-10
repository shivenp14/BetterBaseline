"""Compare JSON fact snapshots using artifact-scoped logical identities."""

import json
import math
import re
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5


_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def _value_key(value):
    # Keep booleans distinct from numbers (Python otherwise equates True and 1).
    if value is None or isinstance(value, bool):
        return (type(value).__name__, value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Fact values must be finite JSON scalars")
        return ("number", Decimal(str(value)))
    if isinstance(value, str):
        numeric = value.strip()
        if _NUMBER.fullmatch(numeric):
            return ("number", Decimal(numeric))
        return ("string", value)
    raise ValueError("Fact values must be JSON scalars")


def _unit_key(unit):
    if unit is None:
        return None
    if not isinstance(unit, str):
        raise ValueError("Fact units must be strings or null")
    # Do not infer aliases, case equivalence, or conversions such as week/day.
    return unit.strip()


def _identity_value(value):
    kind, normalized = _value_key(value)
    if kind != "number":
        return (kind, normalized)
    # Canonicalize exactly without Decimal.normalize's context rounding.
    if normalized == 0:
        return (kind, 0, [0], 0)
    sign, digits, exponent = normalized.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    return (kind, sign, digits, exponent)


def _index(facts):
    indexed = {}
    for fact in facts:
        for field in ("id", "artifact_id", "logical_key"):
            if not isinstance(fact.get(field), str) or not fact[field]:
                raise ValueError(f"Fact {field} must be a nonempty string")
        key = (fact["artifact_id"], fact["logical_key"])
        if key in indexed:
            raise ValueError(f"Duplicate fact identity: {key!r}")
        if "value" not in fact or "unit" not in fact:
            raise ValueError("Facts must include value and unit")
        _value_key(fact["value"])
        _unit_key(fact["unit"])
        indexed[key] = fact
    return indexed


def compare_facts(before, after):
    """Return deterministic Change dictionaries without mutating input facts.

    Match on (artifact_id, logical_key), independent of snapshot IDs, labels,
    and source formatting. IDs use normalized logical change content, independent
    of regenerated snapshot IDs. Input ordering does not affect output ordering.
    """
    old, new = _index(before), _index(after)
    changes = []
    for artifact_id, logical_key in sorted(old.keys() | new.keys()):
        previous = old.get((artifact_id, logical_key))
        replacement = new.get((artifact_id, logical_key))
        if previous is not None and replacement is not None:
            if (_value_key(previous["value"]), _unit_key(previous["unit"])) == (
                _value_key(replacement["value"]), _unit_key(replacement["unit"])
            ):
                continue
            kind = "modified"
        else:
            kind = "added" if previous is None else "removed"
        change = {
            "artifact_id": artifact_id,
            "logical_key": logical_key,
            "before_fact_id": previous["id"] if previous is not None else None,
            "after_fact_id": replacement["id"] if replacement is not None else None,
            "before_value": previous["value"] if previous is not None else None,
            "after_value": replacement["value"] if replacement is not None else None,
            "before_unit": previous["unit"] if previous is not None else None,
            "after_unit": replacement["unit"] if replacement is not None else None,
            "kind": kind,
        }
        logical_change = {
            "artifact_id": artifact_id, "logical_key": logical_key, "kind": kind,
            "before_value": _identity_value(change["before_value"]),
            "after_value": _identity_value(change["after_value"]),
            "before_unit": _unit_key(change["before_unit"]),
            "after_unit": _unit_key(change["after_unit"]),
        }
        identity = json.dumps(logical_change, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        change["id"] = str(uuid5(NAMESPACE_URL, "trialsync:change:" + identity))
        changes.append(change)
    return changes
