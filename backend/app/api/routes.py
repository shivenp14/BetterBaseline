from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.models import Artifact, AuditEvent, Finding, Graph, Items, Study
from app.persistence.repository import ReadRepository

router = APIRouter(prefix="/api")


def get_repository(request: Request) -> ReadRepository:
    return request.app.state.repository


Repository = Annotated[ReadRepository, Depends(get_repository)]


@router.get("/studies", response_model=Items[Study])
def studies(repository: Repository):
    return {"items": repository.list_studies()}


@router.get("/studies/{study_id}/artifacts", response_model=Items[Artifact])
def artifacts(study_id: UUID, repository: Repository):
    return {"items": repository.list_artifacts(study_id)}


@router.get("/studies/{study_id}/graph", response_model=Graph)
def graph(study_id: UUID, repository: Repository):
    return repository.get_graph(study_id)


@router.get("/studies/{study_id}/findings", response_model=Items[Finding])
def findings(study_id: UUID, repository: Repository):
    return {"items": repository.list_findings(study_id)}


@router.get("/studies/{study_id}/audit", response_model=Items[AuditEvent])
def audit(study_id: UUID, repository: Repository):
    return {"items": repository.list_audit(study_id)}
