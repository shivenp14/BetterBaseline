import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from starlette.formparsers import MultiPartParser

from app.api.body_limit import MAX_UPLOAD_BODY_BYTES
from app.api.uploads import MAX_UPLOAD_BYTES
from app.main import create_app
from app.persistence.memory import InMemoryRepository
from app.persistence.storage import LocalPrivateStorage


class UploadStreamTest(unittest.TestCase):
    def stream(self, file_size, length_header=None):
        repository = InMemoryRepository()
        artifact = repository.list_artifacts(repository.list_studies()[0].id)[0]
        preamble = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="source.txt"\r\nContent-Type: text/plain\r\n\r\n'
        suffix = b'\r\n--boundary--\r\n'
        chunks = [preamble] + [b'x' * min(65536, file_size - offset)
                               for offset in range(0, file_size, 65536)] + [suffix]
        total_body = sum(map(len, chunks))
        received = 0
        spooled = 0
        files = []
        messages = []
        on_part_data = MultiPartParser.on_part_data
        on_headers_finished = MultiPartParser.on_headers_finished

        def count_data(parser, data, start, end):
            nonlocal spooled
            if parser._current_part.file:
                spooled += end - start
            on_part_data(parser, data, start, end)

        def track_files(parser):
            on_headers_finished(parser)
            if parser._current_part.file:
                files.append(parser._current_part.file.file)

        async def run(application):
            nonlocal received
            remaining = iter(enumerate(chunks))
            async def receive():
                nonlocal received
                index, chunk = next(remaining)
                received += len(chunk)
                return {'type': 'http.request', 'body': chunk, 'more_body': index < len(chunks)-1}
            async def send(message):
                messages.append(message)
            headers = [(b'content-type', b'multipart/form-data; boundary=boundary')]
            if length_header is not None:
                headers.append((b'content-length', str(length_header).encode()))
            await application({'type': 'http', 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
                'path': f'/api/artifacts/{artifact.id}/versions', 'query_string': b'', 'headers': headers,
                'server': ('testserver', 80), 'client': ('127.0.0.1', 1234), 'root_path': ''}, receive, send)

        with TemporaryDirectory() as folder:
            storage = LocalPrivateStorage(Path(folder))
            application = create_app(repository, storage=storage)
            with patch.object(MultiPartParser, 'on_part_data', count_data), patch.object(MultiPartParser, 'on_headers_finished', track_files):
                asyncio.run(run(application))
            starts = [m for m in messages if m['type'] == 'http.response.start']
            self.assertEqual(len(starts), 1)
            status = starts[0]['status']
            if status == 413:
                self.assertEqual(list(Path(folder).rglob('*')), [])
                self.assertEqual(len(repository.get_artifact(artifact.id).versions), len(artifact.versions))
            self.assertTrue(all(f.closed for f in files), 'Multipart files must close on rejection and success')
        return status, received, spooled, total_body

    def test_oversized_stream_stops_before_full_spooling(self):
        for header in (None, 1, 'untrustworthy'):
            with self.subTest(content_length=header):
                status, received, spooled, total = self.stream(12 * 1024 * 1024, header)
                self.assertEqual(status, 413)
                self.assertLess(received, total)
                self.assertLess(spooled, 12 * 1024 * 1024)
                self.assertLessEqual(spooled, MAX_UPLOAD_BODY_BYTES)

    def test_large_declared_length_rejects_before_reading(self):
        status, received, spooled, _ = self.stream(12 * 1024 * 1024, MAX_UPLOAD_BODY_BYTES + 1)
        self.assertEqual((status, received, spooled), (413, 0, 0))

    def test_file_at_exact_limit_succeeds(self):
        status, _, spooled, _ = self.stream(MAX_UPLOAD_BYTES)
        self.assertEqual(status, 201)
        self.assertEqual(spooled, MAX_UPLOAD_BYTES)
