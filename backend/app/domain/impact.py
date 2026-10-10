"""Deterministic traversal of the prior approved dependency graph."""

import json
from collections import defaultdict, deque
from uuid import NAMESPACE_URL, uuid5


def _records_by_id(records, label):
    indexed = {}
    for record in records:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"{label} id must be a nonempty string")
        if identifier in indexed and indexed[identifier] != record:
            raise ValueError(f"Conflicting {label} id: {identifier}")
        indexed[identifier] = record
    return indexed


def assess_impact(changes, facts, dependencies, *, study_id=None):
    """Return open findings, one per change/affected fact, in stable order.

    Facts must include the old snapshots and every endpoint of the confirmed
    current graph. The caller supplies that graph; tracking='current' alone
    cannot distinguish superseded approved graph snapshots.

    Added facts receive an empty-path link-review finding on their new snapshot;
    no outgoing candidate links are traversed. Action rules and explanation
    generation are subsequent tasks; review_document is the interim fallback.
    Supply study_id from worker context before persisting findings.
    """
    fact_index = _records_by_id(facts, "Fact")
    change_index = _records_by_id(changes, "Change")
    edges = _records_by_id(dependencies, "Dependency")
    adjacency = defaultdict(list)
    for fact in fact_index.values():
        if not isinstance(fact.get("artifact_id"), str) or not fact["artifact_id"]:
            raise ValueError("Fact artifact_id must be a nonempty string")
    for edge_id in sorted(edges):
        edge = edges[edge_id]
        if edge.get("status") != "confirmed" or edge.get("tracking") != "current":
            continue
        for field in ("from_fact_id", "to_fact_id"):
            if edge.get(field) not in fact_index:
                raise ValueError(f"Dependency {edge_id} has missing endpoint {field}")
        adjacency[edge["from_fact_id"]].append(edge)

    findings = []

    def add_finding(change, fact_id, path):
        fact = fact_index[fact_id]
        identity = json.dumps([change["id"], fact_id], separators=(",", ":"))
        findings.append({
            "id": str(uuid5(NAMESPACE_URL, "trialsync:finding:" + identity)),
            "study_id": study_id,
            "change_id": change["id"],
            "affected_fact_id": fact_id,
            "affected_artifact_id": fact["artifact_id"],
            "path_edge_ids": list(path),
            "action": "review_document",
            "explanation": "",
            "sources": [],
            "status": "open",
            "owner_id": None,
            "resolution": None,
        })

    for change_id in sorted(change_index):
        change = change_index[change_id]
        kind = change.get("kind")
        if kind not in ("added", "removed", "modified"):
            raise ValueError(f"Unsupported change kind: {kind!r}")
        if kind == "added":
            if change.get("before_fact_id") is not None:
                raise ValueError("Added changes must have a null before_fact_id")
            target = change.get("after_fact_id")
            if target not in fact_index:
                raise ValueError("Added change requires its after fact snapshot")
            add_finding(change, target, ())
            continue
        root = change.get("before_fact_id")
        if root not in fact_index:
            raise ValueError("Modified/removed change requires its before fact snapshot")
        if kind == "removed" and change.get("after_fact_id") is not None:
            raise ValueError("Removed changes must have a null after_fact_id")
        if kind == "modified" and not change.get("after_fact_id"):
            raise ValueError("Modified changes require an after_fact_id")
        visited = {root}
        queue = deque([(root, ())])
        while queue:
            upstream, path = queue.popleft()
            for edge in adjacency[upstream]:
                target = edge["to_fact_id"]
                if target in visited:
                    continue
                visited.add(target)
                next_path = path + (edge["id"],)
                add_finding(change, target, next_path)
                queue.append((target, next_path))
    return sorted(findings, key=lambda finding: (finding["change_id"], finding["affected_fact_id"]))
