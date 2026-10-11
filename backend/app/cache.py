"""In-memory bounded LRU cache for expensive statistical computations (Issue #68).

Keyed by deterministic SHA-256 digests over (route, model_version, canonical_json_params).
"""

from collections import OrderedDict
import hashlib
import json
from threading import Lock
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel


def make_cache_key(
    route: str,
    model_version: str,
    params: Union[BaseModel, Dict[str, Any]],
) -> str:
    """Generate canonical SHA-256 cache key.

    Serializes route, model version, and normalized parameters with sorted keys
    and compact delimiters.
    """
    if isinstance(params, BaseModel):
        normalized_params = params.model_dump(mode="json")
    elif isinstance(params, dict):
        normalized_params = params
    else:
        normalized_params = str(params)

    payload = {
        "route": route,
        "version": model_version,
        "params": normalized_params,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class BoundedComputeCache:
    """Thread-safe bounded in-process LRU cache."""

    def __init__(self, capacity: int = 256) -> None:
        self.capacity = max(1, capacity)
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            # Move to end to record recent usage
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self.capacity:
                # Evict least recently used (first item)
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)
