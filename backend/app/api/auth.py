"""Remote Supabase identity verification plus fresh database membership checks."""

import os
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api.uploads import StudyAccessDenied
from app.persistence.repository import RecordNotFound, RepositoryUnavailable


class InvalidToken(Exception):
    pass


class AuthUnavailable(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> UUID: ...


class SupabaseTokenVerifier:
    def __init__(self, project_url: str, publishable_key: str, client=None):
        url = urlsplit(project_url)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or
            url.path not in ('', '/') or url.query or url.fragment or
            not publishable_key.startswith('sb_publishable_')):
            raise ValueError('Auth requires an HTTPS project origin and publishable API key')
        self._url = project_url.rstrip('/') + '/auth/v1/user'
        self._key = publishable_key
        self._client = client

    def verify(self, token):
        # API keys are not user access tokens. Only the Auth server verifies identity.
        if token.startswith(('sb_publishable_', 'sb_secret_')):
            raise InvalidToken
        try:
            headers = {'apikey': self._key, 'Authorization': f'Bearer {token}'}
            if self._client is not None:
                response = self._client.get(self._url, headers=headers)
            else:
                with httpx.Client(timeout=5, follow_redirects=False) as client:
                    response = client.get(self._url, headers=headers)
            if response.status_code in (401, 403):
                raise InvalidToken
            if response.status_code != 200:
                raise AuthUnavailable
            user = response.json()
            if user.get('aud') != 'authenticated' or user.get('role') != 'authenticated':
                raise InvalidToken
            return UUID(user['id'])
        except httpx.HTTPError:
            raise AuthUnavailable from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AuthUnavailable from None


class UnconfiguredVerifier:
    def verify(self, token):
        raise AuthUnavailable


def configured_verifier():
    project_url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY')
    if key:
        if not project_url:
            raise ValueError('SUPABASE_URL is required with SUPABASE_PUBLISHABLE_KEY')
        return SupabaseTokenVerifier(project_url, key)
    return UnconfiguredVerifier()  # Missing configuration never enables demo access.


class MemberStudyAccess:
    def __init__(self, repository, user_id):
        self.repository, self.user_id = repository, user_id

    def require_study_access(self, study_id):
        if not self.repository.has_membership(study_id, self.user_id):
            raise StudyAccessDenied


class AuthGuard:
    """Verify once per API request, before FastAPI parses multipart bodies."""

    def __init__(self, app, verifier, repository, mode):
        self.app, self.verifier, self.repository, self.mode = app, verifier, repository, mode

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not (scope['path'] == '/api' or scope['path'].startswith('/api/')) or self.mode == 'demo':
            return await self.app(scope, receive, send)

        def error(status, code, message, headers=None):
            return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}}, headers=headers)

        values = [v for k, v in scope.get('headers', []) if k.lower() == b'authorization']
        response = None
        try:
            if len(values) != 1:
                raise InvalidToken
            authorization = values[0].decode('ascii')
            scheme, _, token = authorization.partition(' ')
            if scheme.lower() != 'bearer' or not token or len(token) > 16384 or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token):
                raise InvalidToken
            user_id = await run_in_threadpool(self.verifier.verify, token)
            if not isinstance(user_id, UUID):
                raise AuthUnavailable
            scope.setdefault('state', {})['user_id'] = user_id
            # Deny nonmember uploads before multipart spooling, too.
            parts = scope['path'].split('/')
            if scope['method'] == 'POST' and len(parts) == 5 and parts[1:3] == ['api', 'artifacts'] and parts[4] == 'versions':
                try:
                    artifact_id = UUID(parts[3])
                except ValueError:
                    artifact_id = None  # Let normal route validation reject malformed IDs.
                if artifact_id is not None:
                    artifact = await run_in_threadpool(self.repository.get_artifact, artifact_id)
                    await run_in_threadpool(MemberStudyAccess(self.repository, user_id).require_study_access, artifact.study_id)
        except (InvalidToken, UnicodeError):
            response = error(401, 'unauthorized', 'A valid Supabase bearer access token is required', {'WWW-Authenticate': 'Bearer'})
        except AuthUnavailable:
            response = error(503, 'auth_unavailable', 'Identity verification is temporarily unavailable')
        except StudyAccessDenied:
            response = error(403, 'forbidden', 'Study access denied')
        except RecordNotFound:
            response = error(404, 'not_found', 'Record not found')
        except RepositoryUnavailable:
            response = error(503, 'repository_unavailable', 'Database reads are temporarily unavailable')
        if response is not None:
            return await response(scope, receive, send)
        await self.app(scope, receive, send)


def cors_origins():
    raw = os.environ.get('CORS_ORIGINS')
    if raw is None:
        return ['http://localhost:3000', 'http://127.0.0.1:3000']
    origins = []
    for value in raw.split(','):
        value = value.strip().rstrip('/')
        if not value:
            continue
        origin = urlsplit(value)
        if origin.scheme not in ('https', 'http') or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment or '*' in value:
            raise ValueError('CORS_ORIGINS must contain exact HTTP(S) origins, without wildcards or paths')
        origins.append(value)
    return origins
