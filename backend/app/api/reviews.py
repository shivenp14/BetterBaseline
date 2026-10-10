"""Human review mutations use a server-selected local actor until #18."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.models import ArtifactVersion, Dependency, DependencyReview, Finding, FindingReview
from app.api.review_policy import ReviewPolicy
from app.api.uploads import Access
from app.persistence.repository import ReviewRepository

router = APIRouter(prefix='/api')


def get_review_repository(request: Request) -> ReviewRepository:
    return request.app.state.repository


def get_review_actor(request: Request) -> UUID:
    return request.app.state.review_actor


def get_review_policy(request: Request) -> ReviewPolicy:
    return request.app.state.review_policy


Actor = Annotated[UUID, Depends(get_review_actor)]
Policy = Annotated[ReviewPolicy, Depends(get_review_policy)]
Repository = Annotated[ReviewRepository, Depends(get_review_repository)]


@router.patch('/dependencies/{dependency_id}', response_model=Dependency)
def confirm_dependency(dependency_id: UUID, patch: DependencyReview, repository: Repository,
                       access: Access, actor: Actor):
    stored = repository.get_dependency(dependency_id)
    access.require_study_access(stored.study_id)
    return repository.confirm_dependency(dependency_id, actor)


@router.patch('/findings/{finding_id}', response_model=Finding)
def update_finding(finding_id: UUID, patch: FindingReview, repository: Repository,
                   access: Access, actor: Actor, policy: Policy):
    finding = repository.get_finding(finding_id)
    access.require_study_access(finding.study_id)
    return repository.update_finding(finding_id, patch, actor, policy)


@router.post('/versions/{version_id}/approve', response_model=ArtifactVersion)
def approve_version(version_id: UUID, repository: Repository, access: Access, actor: Actor, policy: Policy):
    stored = repository.get_version(version_id)
    access.require_study_access(stored.version.study_id)
    return repository.approve_version(version_id, actor, policy)
