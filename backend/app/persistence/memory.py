"""Small synthetic read adapter. Returned records never mutate stored fixtures."""

import json
from importlib.resources import files
from uuid import UUID, uuid4
from datetime import datetime, timezone
from threading import RLock

from pydantic import BaseModel, ConfigDict

from app.api.models import Artifact, ArtifactVersion, AuditEvent, Change, Finding, Graph, Job, Study, UploadReceipt
from app.persistence.repository import RecordNotFound, StoredDependency, StoredJob, StoredVersion, StudyNotFound
from app.api.review_policy import InvalidReview, ReviewConflict, validate_confirmation


class StudyFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study: Study
    artifacts: list[Artifact]
    graph: Graph
    changes: list[Change]
    findings: list[Finding]
    audit: list[AuditEvent]


class InMemoryRepository:
    def __init__(self, fixtures: list[StudyFixture] | None = None):
        if fixtures is None:
            raw = json.loads(files("app.persistence").joinpath("fixtures.json").read_text())
            fixtures = [StudyFixture.model_validate(item) for item in raw]
        self._studies = {item.study.id: item.model_copy(deep=True) for item in fixtures}
        self._jobs: dict[UUID, StoredJob] = {}
        self._paths: dict[UUID, tuple[str, str]] = {}
        self._lock = RLock()
        self._approved = {a.id: min(a.versions, key=lambda v: v.version_number).id if a.versions else None
                          for fixture in self._studies.values() for a in fixture.artifacts}
        self._members = {fixture.study.id: {event.actor_id for event in fixture.audit}
                         for fixture in self._studies.values()}

    def _get(self, study_id: UUID) -> StudyFixture:
        try:
            return self._studies[study_id].model_copy(deep=True)
        except KeyError:
            raise StudyNotFound from None

    def list_studies(self) -> list[Study]:
        return [item.study.model_copy(deep=True) for item in self._studies.values()]

    def list_studies_for_user(self, user_id):
        with self._lock:
            return [s for s in self.list_studies() if user_id in self._members[s.id]]

    def has_membership(self, study_id, user_id):
        with self._lock:
            return user_id in self._members.get(study_id, set())

    def get_version_by_storage_path(self, path):
        with self._lock:
            for version_id, (stored_path, _) in self._paths.items():
                if stored_path == path:
                    return self.get_version(version_id)
        raise RecordNotFound

    def list_artifacts(self, study_id: UUID) -> list[Artifact]:
        return self._get(study_id).artifacts

    def get_graph(self, study_id: UUID) -> Graph:
        return self._get(study_id).graph

    def list_findings(self, study_id: UUID) -> list[Finding]:
        return self._get(study_id).findings

    def list_audit(self, study_id: UUID) -> list[AuditEvent]:
        return self._get(study_id).audit

    def get_artifact(self, artifact_id: UUID) -> Artifact:
        with self._lock:
            for fixture in self._studies.values():
                for artifact in fixture.artifacts:
                    if artifact.id == artifact_id:
                        return artifact.model_copy(deep=True)
        raise RecordNotFound

    def create_version_job(self, artifact_id, version_id, job_id, filename, storage_path, content_hash):
        with self._lock:
            artifact = self.get_artifact(artifact_id)
            previous = max(artifact.versions, key=lambda version: version.version_number, default=None)
            version = ArtifactVersion(id=version_id, artifact_id=artifact_id, study_id=artifact.study_id,
                version_number=previous.version_number + 1 if previous else 1,
                previous_version_id=previous.id if previous else None, filename=filename, status="uploaded")
            job = Job(id=job_id, version_id=version_id, status="queued", stage="queued", error=None)
            for existing in self._studies[artifact.study_id].artifacts:
                if existing.id == artifact_id:
                    existing.versions.append(version)
                    break
            self._paths[version_id] = (storage_path, content_hash)
            self._jobs[job_id] = StoredJob(job, artifact.study_id)
            return UploadReceipt(version=version.model_copy(deep=True), job=job.model_copy(deep=True))

    def get_job(self, job_id):
        with self._lock:
            try:
                stored = self._jobs[job_id]
            except KeyError:
                raise RecordNotFound from None
            return StoredJob(stored.job.model_copy(deep=True), stored.study_id)

    def get_version(self, version_id):
        with self._lock:
            for fixture in self._studies.values():
                for artifact in fixture.artifacts:
                    for version in artifact.versions:
                        if version.id == version_id:
                            path, digest = self._paths.get(version_id, (None, None))
                            return StoredVersion(version.model_copy(deep=True), path, digest)
        raise RecordNotFound

    def get_dependency(self, dependency_id):
        with self._lock:
            for fixture in self._studies.values():
                for edge in fixture.graph.dependencies:
                    if edge.id == dependency_id:
                        return StoredDependency(edge.model_copy(deep=True), fixture.study.id)
        raise RecordNotFound

    def get_finding(self, finding_id):
        with self._lock:
            for fixture in self._studies.values():
                for finding in fixture.findings:
                    if finding.id == finding_id:
                        return finding.model_copy(deep=True)
        raise RecordNotFound

    def _require_reviewer(self, study_id, actor):
        if actor not in self._members[study_id]:
            raise InvalidReview('Acting reviewer must be a study member')

    def _append_review_audit(self, fixture, actor, action, entity_id):
        fixture.audit.append(AuditEvent(id=uuid4(), study_id=fixture.study.id, actor_id=actor,
            action=action, entity_id=entity_id, created_at=datetime.now(timezone.utc)))

    def confirm_dependency(self, dependency_id, actor):
        with self._lock:
            stored = self.get_dependency(dependency_id)
            self._require_reviewer(stored.study_id, actor)
            fixture = self._get(stored.study_id)
            edge = next(e for e in fixture.graph.dependencies if e.id == dependency_id)
            validate_confirmation(edge, fixture.graph, self._approved)
            if edge.status == 'confirmed':
                return edge
            edge.status = 'confirmed'
            self._append_review_audit(fixture, actor, 'dependency.confirmed', edge.id)
            self._studies[fixture.study.id] = fixture
            return edge.model_copy(deep=True)

    def _approve_memory_version(self, fixture, approved, version_id, actor, policy):
        versions = [v for a in fixture.artifacts for v in a.versions]
        version = next((v for v in versions if v.id == version_id), None)
        if version is None or version.status != 'ready':
            raise InvalidReview('Replacement must be a ready version in this study')
        jobs = [j.job for j in self._jobs.values() if j.job.version_id == version_id]
        if any(j.status != 'succeeded' for j in jobs):
            raise InvalidReview('Replacement processing must have succeeded')
        if approved.get(version.artifact_id) == version_id:
            return version
        old = next((v for v in versions if v.id == approved.get(version.artifact_id)), None)
        if old and version.version_number <= old.version_number:
            raise ReviewConflict('Approval cannot roll back an artifact to an older snapshot')
        projections = policy.projection(fixture.graph, approved, version)
        if any(e.status != 'confirmed' or e.tracking != 'current' for e in projections):
            raise InvalidReview('Projection must retain confirmed current links')
        fixture.graph.dependencies.extend(projections)
        approved[version.artifact_id] = version_id
        self._append_review_audit(fixture, actor, 'version.approved', version_id)
        return version

    def approve_version(self, version_id, actor, policy):
        with self._lock:
            stored = self.get_version(version_id)
            self._require_reviewer(stored.version.study_id, actor)
            fixture = self._get(stored.version.study_id)
            approved = self._approved.copy()
            version = self._approve_memory_version(fixture, approved, version_id, actor, policy)
            self._studies[fixture.study.id], self._approved = fixture, approved
            return version.model_copy(deep=True)

    def update_finding(self, finding_id, patch, actor, policy):
        with self._lock:
            current = self.get_finding(finding_id)
            self._require_reviewer(current.study_id, actor)
            updated = policy.finding(current, patch)
            if updated.owner_id is not None and updated.owner_id not in self._members[current.study_id]:
                raise InvalidReview('Finding owner must be a study member')
            if updated == current:
                return updated
            fixture = self._get(current.study_id)
            approved = self._approved.copy()
            if updated.resolution is not None and updated.resolution.decision == 'updated':
                version_id = updated.resolution.replacement_version_id
                try:
                    stored = self.get_version(version_id)
                except RecordNotFound:
                    raise InvalidReview('Replacement version does not exist') from None
                affected = next(f for f in fixture.graph.facts if f.id == current.affected_fact_id)
                affected_version = self.get_version(affected.version_id).version
                if stored.version.artifact_id != current.affected_artifact_id or stored.version.version_number <= affected_version.version_number:
                    raise InvalidReview('Replacement must be a newer version of the affected artifact')
                self._approve_memory_version(fixture, approved, version_id, actor, policy)
            fixture.findings = [updated if f.id == finding_id else f for f in fixture.findings]
            self._append_review_audit(fixture, actor, 'finding.updated', finding_id)
            self._studies[current.study_id], self._approved = fixture, approved
            return updated.model_copy(deep=True)
