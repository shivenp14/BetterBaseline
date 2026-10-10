"""Small explicit action policy; returned actions request human review."""

from collections.abc import Mapping


_RULES = {
    (relationship, kind): "review_document"
    for relationship in ("defines", "describes", "calculated_from", "requires", "covered_by")
    for kind in ("document", "protocol", "analysis_plan", "visit_schedule", "report")
}
_RULES.update({
    (relationship, "analysis_result"): "rerun_analysis"
    for relationship in ("defines", "calculated_from", "requires")
})


def impact_action(relationship, artifact):
    """Select an action from an artifact record or explicit kind string.

    Unknown/missing relationship or kind receives review_document. No kind is
    inferred from filenames, fact labels, source values, or other path edges.
    """
    kind = artifact.get("kind") if isinstance(artifact, Mapping) else artifact
    if not isinstance(relationship, str) or not isinstance(kind, str):
        return "review_document"
    return _RULES.get((relationship, kind), "review_document")
