"""Source-backed descriptions of stored changes and dependency paths."""

import json
from copy import deepcopy


def explain_impact(change, affected, path, facts, edges, action):
    """Return readable text and deduplicated source objects, without edits.

    Missing evidence is stated explicitly. Quotes are returned as references,
    never interpreted as instructions or used to invent relationships.
    """
    before = facts.get(change.get("before_fact_id"))
    after = facts.get(change.get("after_fact_id"))
    source_fact = before or after or {}

    def label(fact):
        return f"{fact.get('label') or fact.get('logical_key') or fact['id']} ({fact['id']})"

    def value(side, snapshot):
        scalar = json.dumps(change.get(side + "_value"), ensure_ascii=False)
        unit = change.get(side + "_unit", snapshot.get("unit") if snapshot else None)
        return f"{scalar} [unit: {json.dumps(unit, ensure_ascii=False)}]"

    name = label(source_fact) if source_fact else change["logical_key"]
    if change["kind"] == "added":
        text = f"Added {name}: {value('after', after)}."
    elif change["kind"] == "removed":
        text = f"Removed {name}: previously {value('before', before)}."
    else:
        text = f"Changed {name} from {value('before', before)} to {value('after', after)}."

    references = []
    seen = set()

    def add_source(source):
        if not isinstance(source, dict) or not source:
            return
        key = json.dumps(source, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            references.append(deepcopy(source))

    for fact in (before, after):
        if fact:
            add_source(fact.get("source"))
    if path:
        segments = []
        for edge_id in path:
            edge = edges[edge_id]
            upstream, dependent = facts[edge["from_fact_id"]], facts[edge["to_fact_id"]]
            segments.append(f"{label(upstream)} --{edge.get('relationship') or 'unsupported relationship'} [{edge_id}]--> {label(dependent)}")
            add_source(upstream.get("source"))
            for source in edge.get("evidence") or []:
                add_source(source)
            add_source(dependent.get("source"))
        text += f" Affected fact: {label(affected)}. Confirmed current dependency path: " + "; ".join(segments) + "."
    else:
        text += f" Fact requiring link review: {label(affected)}. No established dependency path; downstream impact has not been inferred."
    add_source(affected.get("source"))
    requests = {
        "review_document": "Request document review",
        "rerun_analysis": "Request reanalysis and review of its output",
        "review_support": "Request support coverage review",
    }
    text += " " + requests[action] + "; no update or analysis has been performed."
    if references:
        citations = [f"{source.get('fragment_id') or 'unknown fragment'} at {source.get('locator') or 'unknown locator'}" for source in references]
        text += " Source references: " + "; ".join(citations) + "."
    else:
        text += " Source references are unavailable in the supplied records."
    if change.get("after_fact_id") and after is None:
        text += " The replacement fact snapshot was not supplied; its source is unavailable."
    return text, references
