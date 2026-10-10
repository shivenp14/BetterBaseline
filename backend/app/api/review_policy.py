"""Replaceable local review/projection policy until domain #33/#34 integrate."""

from typing import Protocol
from uuid import UUID, NAMESPACE_URL, uuid5

from app.api.models import ArtifactVersion, Dependency, Fact, Finding, FindingReview, Graph


class InvalidReview(Exception):
    pass


class ReviewConflict(Exception):
    pass


class ReviewPolicy(Protocol):
    def finding(self, current: Finding, patch: FindingReview) -> Finding: ...
    def projection(self, graph: Graph, approved: dict[UUID, UUID | None], version: ArtifactVersion) -> list[Dependency]: ...


class LocalReviewPolicy:
    def finding(self, current, patch):
        fields = patch.model_dump(exclude_unset=True)
        if not fields or ('status' in fields and fields['status'] is None):
            raise InvalidReview('A nonempty review patch with a valid status is required')
        updated = Finding.model_validate(current.model_dump() | fields)
        if current.status in ('resolved', 'dismissed') and updated != current:
            raise ReviewConflict('Closed findings cannot be edited or reopened')
        resolution = updated.resolution
        if resolution is not None and len(resolution.note) > 2000:
            raise InvalidReview('Resolution note exceeds 2000 characters')
        if updated.status in ('resolved', 'dismissed'):
            if resolution is None or not resolution.note.strip():
                raise InvalidReview('Closing a finding requires recorded justification')
            if resolution.decision == 'reanalysis_requested':
                raise InvalidReview('Requested reanalysis must remain in_review')
            if updated.status == 'dismissed' and resolution.decision != 'no_change':
                raise InvalidReview('Dismissal requires a justified no_change decision')
        elif resolution is not None:
            if (updated.status != 'in_review' or resolution.decision != 'reanalysis_requested'
                or not resolution.note.strip()):
                raise InvalidReview('Only justified reanalysis_requested can remain pending in_review')
        if resolution is not None:
            if resolution.decision == 'updated' and resolution.replacement_version_id is None:
                raise InvalidReview('Updated resolution requires a replacement version')
            if resolution.decision != 'updated' and resolution.replacement_version_id is not None:
                raise InvalidReview('Only an updated resolution can approve a replacement version')
        if current.status == 'in_review' and updated.status == 'open':
            raise ReviewConflict('An active review cannot return to open')
        return updated

    def projection(self, graph, approved, version):
        candidates = {f.logical_key: f for f in graph.facts if f.version_id == version.id}
        old_ids = {v for v in approved.values() if v is not None}
        active = {f.id: f for f in graph.facts if f.version_id in old_ids}
        projected = []
        for edge in graph.dependencies:
            if edge.status != 'confirmed' or edge.tracking != 'current':
                continue
            if edge.from_fact_id not in active or edge.to_fact_id not in active:
                continue
            def replacement(fact: Fact):
                if fact.artifact_id != version.artifact_id:
                    return fact.id
                mapped = candidates.get(fact.logical_key)
                if mapped is None:
                    raise ReviewConflict('Current edge target is missing from replacement; explicit link review is required')
                return mapped.id
            from_id, to_id = replacement(active[edge.from_fact_id]), replacement(active[edge.to_fact_id])
            if (from_id, to_id) != (edge.from_fact_id, edge.to_fact_id):
                projected.append(edge.model_copy(update={
                    'id': uuid5(NAMESPACE_URL, f'trialsync/approved/{version.id}/{edge.id}'),
                    'from_fact_id': from_id, 'to_fact_id': to_id}))
        return projected


def validate_confirmation(edge: Dependency, graph: Graph, approved: dict[UUID, UUID | None]):
    facts = {f.id: f for f in graph.facts}
    if edge.from_fact_id == edge.to_fact_id:
        raise InvalidReview('Self dependencies cannot be confirmed')
    endpoints = [facts.get(edge.from_fact_id), facts.get(edge.to_fact_id)]
    if any(f is None for f in endpoints):
        raise InvalidReview('Dependency endpoints must exist in the same study')
    if edge.tracking == 'current' and any(approved.get(f.artifact_id) != f.version_id for f in endpoints):
        raise ReviewConflict('Confirm current dependencies against approved snapshots')
    sources = {f.source.fragment_id: f.source for f in graph.facts}
    if not edge.evidence or any(sources.get(source.fragment_id) != source or not source.quote.strip()
                                or not source.locator.strip() for source in edge.evidence):
        raise InvalidReview('Confirmation requires retained study source evidence')
