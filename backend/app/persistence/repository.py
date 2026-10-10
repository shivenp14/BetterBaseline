"""Synchronous read port; raise StudyNotFound for an unknown study."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.api.models import Artifact, ArtifactVersion, AuditEvent, Dependency, Finding, FindingReview, Graph, Job, Study, UploadReceipt


class StudyNotFound(Exception):
    pass


class RepositoryUnavailable(Exception):
    pass


class RecordNotFound(Exception):
    pass


class UploadOutcomeUnknown(Exception):
    """Commit failed after it was sent; keep the object for reconciliation."""


@dataclass
class StoredJob:
    job: Job
    study_id: UUID


@dataclass
class StoredVersion:
    version: ArtifactVersion
    storage_path: str | None
    content_hash: str | None


@dataclass
class StoredDependency:
    dependency: Dependency
    study_id: UUID


class ReadRepository(Protocol):
    def list_studies(self) -> list[Study]: ...
    def list_artifacts(self, study_id: UUID) -> list[Artifact]: ...
    def get_graph(self, study_id: UUID) -> Graph: ...
    def list_findings(self, study_id: UUID) -> list[Finding]: ...
    def list_audit(self, study_id: UUID) -> list[AuditEvent]: ...


class UploadRepository(ReadRepository, Protocol):
    def get_artifact(self, artifact_id: UUID) -> Artifact: ...
    def create_version_job(self, artifact_id: UUID, version_id: UUID, job_id: UUID,
                           filename: str, storage_path: str, content_hash: str) -> UploadReceipt: ...
    def get_job(self, job_id: UUID) -> StoredJob: ...
    def get_version(self, version_id: UUID) -> StoredVersion: ...


class ReviewRepository(UploadRepository, Protocol):
    def get_dependency(self, dependency_id: UUID) -> StoredDependency: ...
    def get_finding(self, finding_id: UUID) -> Finding: ...
    def confirm_dependency(self, dependency_id: UUID, actor: UUID) -> Dependency: ...
    def update_finding(self, finding_id: UUID, patch: FindingReview, actor: UUID, policy) -> Finding: ...
    def approve_version(self, version_id: UUID, actor: UUID, policy) -> ArtifactVersion: ...
