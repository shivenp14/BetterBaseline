"""Small synthetic read adapter. Returned records never mutate stored fixtures."""

import json
from importlib.resources import files
from uuid import UUID
from threading import RLock

from pydantic import BaseModel, ConfigDict

from app.api.models import Artifact, ArtifactVersion, AuditEvent, Change, Finding, Graph, Job, Study, UploadReceipt
from app.persistence.repository import RecordNotFound, StoredJob, StoredVersion, StudyNotFound


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

    def _get(self, study_id: UUID) -> StudyFixture:
        try:
            return self._studies[study_id].model_copy(deep=True)
        except KeyError:
            raise StudyNotFound from None

    def list_studies(self) -> list[Study]:
        return [item.study.model_copy(deep=True) for item in self._studies.values()]

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
