"""Local-only unauthenticated fixture API; use trialsync-api or python -m app.main."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.routes import router
from app.persistence.memory import InMemoryRepository
from app.persistence.repository import ReadRepository, StudyNotFound


def error(status: int, code: str, message: str, headers=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def create_app(repository: ReadRepository | None = None) -> FastAPI:
    application = FastAPI(title="TrialSync fixture API", version="0.1.0")
    application.state.repository = repository if repository is not None else InMemoryRepository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )

    @application.exception_handler(StudyNotFound)
    async def study_not_found(request: Request, exc: StudyNotFound):
        return error(404, "study_not_found", "Study not found")

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return error(422, "invalid_request", "Request parameters are invalid")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(exc.status_code, "http_error", str(exc.detail), exc.headers)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    application.include_router(router)
    return application


app = create_app()


def run():
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
