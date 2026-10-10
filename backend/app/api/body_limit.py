"""Bound upload streams before multipart parsing/spooling, regardless of headers."""

from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException

from app.api.uploads import MAX_UPLOAD_BYTES

# Multipart headers/boundaries count toward a separate, small envelope allowance.
MAX_UPLOAD_BODY_BYTES = MAX_UPLOAD_BYTES + 64 * 1024


class UploadBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or scope['method'] != 'POST' or
            not scope['path'].startswith('/api/artifacts/') or not scope['path'].endswith('/versions')):
            return await self.app(scope, receive, send)
        response = JSONResponse(status_code=413, content={'error': {
            'code': 'upload_too_large', 'message': 'Upload body exceeds the 10 MiB file plus 64 KiB multipart limit'}})
        for name, value in scope.get('headers', []):
            if name.lower() == b'content-length':
                try:
                    if int(value) > MAX_UPLOAD_BODY_BYTES:
                        return await response(scope, receive, send)
                except ValueError:
                    pass  # Byte counting below is authoritative.
        received = 0
        exceeded = False
        responded = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > MAX_UPLOAD_BODY_BYTES:
                    exceeded = True
                    # Starlette closes already-spooled files on this exception.
                    raise MultiPartException('Upload body limit exceeded')
            return message

        async def limited_send(message):
            nonlocal responded
            if exceeded:
                if not responded:
                    responded = True
                    await response(scope, receive, send)
            else:
                await send(message)

        await self.app(scope, limited_receive, limited_send)
