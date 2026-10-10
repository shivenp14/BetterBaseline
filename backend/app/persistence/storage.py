"""Private immutable objects, with short-lived download capabilities."""

import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import secrets
import time
from typing import Protocol
from urllib.parse import quote, urlencode

import httpx


class StorageUnavailable(Exception):
    pass


class InvalidSourceToken(Exception):
    pass


class ObjectAlreadyExists(Exception):
    pass


class PrivateStorage(Protocol):
    def put(self, path: str, content: bytes, content_type: str) -> None: ...
    def delete(self, path: str) -> None: ...
    def signed_url(self, path: str, base_url: str) -> str: ...


def check_path(path: str) -> None:
    key = PurePosixPath(path)
    if not path or key.is_absolute() or ".." in key.parts or "\\" in path:
        raise ValueError("Invalid private object path")


class LocalPrivateStorage:
    def __init__(self, root: Path, signing_key: bytes | None = None, ttl_seconds: int = 60):
        self.root = root.resolve()
        self._key = signing_key or secrets.token_bytes(32)
        self._ttl = ttl_seconds

    def _path(self, key: str) -> Path:
        check_path(key)
        result = (self.root / key).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError("Invalid private object path")
        return result

    def put(self, path, content, content_type):
        target = self._path(path)
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
        except FileExistsError:
            raise ObjectAlreadyExists from None
        except OSError:
            raise StorageUnavailable from None

    def delete(self, path):
        try:
            self._path(path).unlink(missing_ok=True)
        except OSError:
            raise StorageUnavailable from None

    def _signature(self, path: str, expires: int) -> str:
        return hmac.new(self._key, f"{path}\n{expires}".encode(), hashlib.sha256).hexdigest()

    def signed_url(self, path, base_url):
        if not self._path(path).is_file():
            raise FileNotFoundError
        expires = int(time.time()) + self._ttl
        query = urlencode(dict(path=path, expires=expires, signature=self._signature(path, expires)))
        return f"{base_url.rstrip('/')}/api/private-source?{query}"

    def download_path(self, path: str, expires: int, signature: str) -> Path:
        if expires <= time.time() or not hmac.compare_digest(self._signature(path, expires), signature):
            raise InvalidSourceToken
        try:
            target = self._path(path)
        except ValueError:
            raise InvalidSourceToken from None
        if not target.is_file():
            raise FileNotFoundError
        return target


class SupabasePrivateStorage:
    def __init__(self, project_url: str, service_role_key: str, bucket: str, client=None):
        if not project_url.startswith("https://") or not service_role_key or not bucket:
            raise ValueError("Private Supabase storage requires HTTPS URL, backend service-role key, and bucket")
        self._base = project_url.rstrip("/") + "/storage/v1"
        self._bucket = quote(bucket, safe="")
        self._headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}
        self._client = client

    def _request(self, method, path, **kwargs):
        try:
            headers = self._headers | kwargs.pop("headers", {})
            if self._client is None:
                with httpx.Client(timeout=30) as client:
                    response = client.request(method, self._base + path, headers=headers, **kwargs)
            else:
                response = self._client.request(method, self._base + path, headers=headers, **kwargs)
            if method == "POST" and "/object/" in path and "/sign/" not in path:
                duplicate = response.status_code == 409
                if response.status_code == 400:
                    try:
                        body = response.json()
                        duplicate = isinstance(body, dict) and (body.get("error") == "Duplicate" or
                            str(body.get("message", "")).lower() in ("asset already exists", "the resource already exists"))
                    except ValueError:
                        pass
                if duplicate:
                    raise ObjectAlreadyExists
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            raise StorageUnavailable from None

    def _private_bucket(self):
        try:
            bucket = self._request("GET", f"/bucket/{self._bucket}").json()
            if bucket.get("public") is not False:
                raise StorageUnavailable
        except (ValueError, AttributeError):
            raise StorageUnavailable from None

    def put(self, path, content, content_type):
        check_path(path)
        self._private_bucket()
        self._request("POST", f"/object/{self._bucket}/{quote(path, safe='/')}", content=content,
                      headers={"Content-Type": content_type, "x-upsert": "false"})

    def delete(self, path):
        check_path(path)
        self._request("DELETE", f"/object/{self._bucket}", json={"prefixes": [path]})

    def signed_url(self, path, base_url):
        check_path(path)
        self._private_bucket()
        try:
            body = self._request("POST", f"/object/sign/{self._bucket}/{quote(path, safe='/')}",
                                 json={"expiresIn": 60}).json()
            relative_url = body["signedURL"]
            if not isinstance(relative_url, str) or not relative_url.startswith("/object/sign/"):
                raise StorageUnavailable
            return self._base + relative_url
        except (ValueError, KeyError, TypeError):
            raise StorageUnavailable from None


def configured_storage() -> PrivateStorage:
    values = [os.environ.get(name) for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_STORAGE_BUCKET")]
    if any(values):
        if not all(values):
            raise ValueError("Set all three private Supabase storage variables")
        return SupabasePrivateStorage(*values)
    root = Path(os.environ.get("LOCAL_STORAGE_ROOT") or str(Path(__file__).resolve().parents[2] / ".private-uploads"))
    return LocalPrivateStorage(root)
