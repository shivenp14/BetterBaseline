"""Private uploads, job polling, and source capabilities with study access checks."""

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.models import Job, SourceURL, UploadReceipt
from app.persistence.repository import UploadOutcomeUnknown, UploadRepository
from app.persistence.storage import InvalidSourceToken, LocalPrivateStorage, ObjectAlreadyExists, PrivateStorage

router = APIRouter(prefix="/api")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


class StudyAccessDenied(Exception):
    pass


class StudyAccess(Protocol):
    def require_study_access(self, study_id: UUID) -> None: ...


class LocalDemoAccess:
    """Access policy selected only by explicit localhost demo mode."""
    def require_study_access(self, study_id: UUID) -> None:
        pass


def get_upload_repository(request: Request) -> UploadRepository:
    return request.app.state.repository


def get_storage(request: Request) -> PrivateStorage:
    return request.app.state.storage


def get_study_access(request: Request):
    if request.app.state.auth_mode == 'required':
        from app.api.auth import MemberStudyAccess
        return MemberStudyAccess(request.app.state.repository, request.state.user_id)
    return request.app.state.study_access


Repository = Annotated[UploadRepository, Depends(get_upload_repository)]
Storage = Annotated[PrivateStorage, Depends(get_storage)]
Access = Annotated[StudyAccess, Depends(get_study_access)]


@router.post("/artifacts/{artifact_id}/versions", response_model=UploadReceipt, status_code=201)
def upload_version(artifact_id: UUID, repository: Repository, storage: Storage, access: Access,
                   file: UploadFile = File(...)):
    try:
        artifact = repository.get_artifact(artifact_id)
        access.require_study_access(artifact.study_id)
        filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
        if not filename or filename in (".", "..") or len(filename.encode("utf-8")) > 240 or any(ord(char) < 32 for char in filename):
            raise HTTPException(422, "A valid filename is required")
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            raise HTTPException(422, "The uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds the 10 MiB limit")
        version_id, job_id = uuid4(), uuid4()
        path = f"{artifact.study_id}/{artifact.id}/{version_id}/{filename}"
        digest = hashlib.sha256(content).hexdigest()
        try:
            storage.put(path, content, file.content_type or "application/octet-stream")
            return repository.create_version_job(artifact.id, version_id, job_id, filename, path, digest)
        except ObjectAlreadyExists:
            raise HTTPException(503, "Object path collision; retry the upload") from None
        except UploadOutcomeUnknown:
            # Deleting now could break a version whose COMMIT succeeded remotely.
            logger.error("Upload commit outcome unknown for version %s and job %s; retain object %s", version_id, job_id, path)
            raise HTTPException(503, f"Upload outcome unknown; reconcile version {version_id} and job {job_id} before retrying") from None
        except Exception:
            try:
                storage.delete(path)
            except Exception:
                logger.error("Failed upload cleanup for object %s; manual reconciliation required", path)
                raise HTTPException(503, "Upload failed and object cleanup needs reconciliation") from None
            raise
    finally:
        file.file.close()


@router.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: UUID, repository: Repository, access: Access):
    stored = repository.get_job(job_id)
    access.require_study_access(stored.study_id)
    return stored.job


@router.get("/versions/{version_id}/source", response_model=SourceURL)
def get_source(version_id: UUID, request: Request, response: Response, repository: Repository, storage: Storage, access: Access):
    stored = repository.get_version(version_id)
    access.require_study_access(stored.version.study_id)
    if stored.storage_path is None:
        raise HTTPException(404, "Source file is unavailable for this fixture version")
    response.headers['Cache-Control'] = 'private, no-store'
    return SourceURL(url=storage.signed_url(stored.storage_path, str(request.base_url)))


@router.get("/private-source", include_in_schema=False)
def download_source(path: str, expires: int, signature: str, storage: Storage, repository: Repository, access: Access):
    if not isinstance(storage, LocalPrivateStorage):
        raise HTTPException(404, "Source route is unavailable")
    try:
        source = storage.download_path(path, expires, signature)
    except InvalidSourceToken:
        raise HTTPException(403, "Source URL is invalid or expired") from None
    stored = repository.get_version_by_storage_path(path)
    access.require_study_access(stored.version.study_id)
    return FileResponse(source, filename=source.name, headers={"Cache-Control": "private, no-store"})
