"""Synchronous read port; raise StudyNotFound for an unknown study."""

from typing import Protocol
from uuid import UUID

from app.api.models import Artifact, AuditEvent, Finding, Graph, Study


class StudyNotFound(Exception):
    pass


class RepositoryUnavailable(Exception):
    pass


class ReadRepository(Protocol):
    def list_studies(self) -> list[Study]: ...
    def list_artifacts(self, study_id: UUID) -> list[Artifact]: ...
    def get_graph(self, study_id: UUID) -> Graph: ...
    def list_findings(self, study_id: UUID) -> list[Finding]: ...
    def list_audit(self, study_id: UUID) -> list[AuditEvent]: ...
