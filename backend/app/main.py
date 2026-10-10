"""Authenticated API; the local CLI binds to loopback."""

import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.exceptions import HTTPException

from app.api.routes import router
from app.api.body_limit import UploadBodyLimit
from app.api.auth import AuthGuard, configured_verifier, cors_origins
from app.api.review_policy import InvalidReview, LocalReviewPolicy, ReviewConflict
from app.api.reviews import router as review_router
from app.persistence.seed import DEMO_ACTOR_ID
from app.api.uploads import LocalDemoAccess, StudyAccessDenied, router as upload_router
from app.persistence.memory import InMemoryRepository
from app.persistence.repository import ReadRepository, RecordNotFound, RepositoryUnavailable, StudyNotFound
from app.persistence.storage import PrivateStorage, StorageUnavailable, configured_storage


def error(status: int, code: str, message: str, headers=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def create_app(repository: ReadRepository | None = None, storage: PrivateStorage | None = None, study_access=None,
               review_actor=None, review_policy=None, auth_mode=None, token_verifier=None) -> FastAPI:
    application = FastAPI(title="TrialSync API", version="0.1.0")
    if repository is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            from app.persistence.postgres import PostgresRepository

            repository = PostgresRepository(database_url)
        else:
            repository = InMemoryRepository()
    application.state.repository = repository
    application.state.storage = storage if storage is not None else configured_storage()
    application.state.study_access = study_access if study_access is not None else LocalDemoAccess()
    application.state.review_actor = review_actor if review_actor is not None else DEMO_ACTOR_ID
    application.state.review_policy = review_policy if review_policy is not None else LocalReviewPolicy()
    mode = auth_mode if auth_mode is not None else os.environ.get('TRIALSYNC_AUTH_MODE', 'required')
    if mode not in ('required', 'demo'):
        raise ValueError('TRIALSYNC_AUTH_MODE must be required or demo')
    application.state.auth_mode = mode
    application.add_middleware(UploadBodyLimit)
    application.add_middleware(AuthGuard, verifier=token_verifier if token_verifier is not None else configured_verifier(),
                               repository=repository, mode=mode)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Content-Type", "Authorization"],
    )

    @application.exception_handler(StudyNotFound)
    async def study_not_found(request: Request, exc: StudyNotFound):
        return error(404, "study_not_found", "Study not found")

    @application.exception_handler(RecordNotFound)
    async def record_not_found(request: Request, exc: RecordNotFound):
        return error(404, "not_found", "Record not found")

    @application.exception_handler(InvalidReview)
    async def invalid_review(request: Request, exc: InvalidReview):
        return error(422, 'invalid_review', str(exc))

    @application.exception_handler(ReviewConflict)
    async def review_conflict(request: Request, exc: ReviewConflict):
        return error(409, 'review_conflict', str(exc))

    @application.exception_handler(StudyAccessDenied)
    async def access_denied(request: Request, exc: StudyAccessDenied):
        return error(403, "forbidden", "Study access denied")

    @application.exception_handler(StorageUnavailable)
    async def storage_unavailable(request: Request, exc: StorageUnavailable):
        return error(503, "storage_unavailable", "Private storage is temporarily unavailable")

    @application.exception_handler(FileNotFoundError)
    async def source_not_found(request: Request, exc: FileNotFoundError):
        return error(404, "source_not_found", "Source file not found")

    @application.exception_handler(RepositoryUnavailable)
    async def repository_unavailable(request: Request, exc: RepositoryUnavailable):
        return error(503, "repository_unavailable", "Database reads are temporarily unavailable")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error(422, "invalid_request", "Request parameters are invalid")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(exc.status_code, "http_error", str(exc.detail), exc.headers)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    # Describe the middleware-enforced bearer contract for Swagger/API clients.
    security = [Depends(HTTPBearer(auto_error=False, scheme_name='SupabaseBearer'))] if mode == 'required' else None
    application.include_router(router, dependencies=security)
    application.include_router(upload_router, dependencies=security)
    application.include_router(review_router, dependencies=security)
    return application


app = create_app()


def run():
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
