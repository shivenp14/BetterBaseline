"""Small synthetic read adapter. Returned records never mutate stored fixtures."""

import json
from importlib.resources import files
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.api.models import Artifact, AuditEvent, Change, Finding, Graph, Study
from app.persistence.repository import StudyNotFound


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
