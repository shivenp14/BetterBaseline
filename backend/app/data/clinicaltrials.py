"""Optional synchronous registry adapter, registered after #68/#67 handoff.

Fixed API v2 host, redirects rejected, 8-second per-attempt timeout, at most one
retry for timeout/transport/5xx, 1 MiB body ceiling, 15-minute TTL and 128-entry
LRU. Errors are explicit; no registry failure can alter manual/preset inputs.
No module-level request occurs and no planning assumption is extracted.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from http.client import HTTPException
import json
import re
from threading import Lock
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .normalize import normalize_study

API_ROOT = 'https://clinicaltrials.gov/api/v2/studies/'
TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 900
CACHE_CAPACITY = 128
MAX_RESPONSE_BYTES = 1_048_576


class TrialLookupError(Exception):
    """Stable adapter error codes; the future router owns HTTP serialization."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _reject_constant(value):
    raise ValueError(f'Invalid JSON numeric constant: {value}')


class ClinicalTrialsClient:
    def __init__(self, *, opener=None, clock=time.monotonic,
                 now=lambda: datetime.now(timezone.utc)):
        # Preserve standard proxy/CA settings; never follow a redirect off host.
        self._opener = opener if opener is not None else build_opener(_NoRedirect())
        self._clock = clock
        self._now = now
        self._cache = OrderedDict()
        self._lock = Lock()

    def lookup(self, nct_id):
        if not isinstance(nct_id, str) or re.fullmatch(r'NCT[0-9]{8}', nct_id) is None:
            raise TrialLookupError('INVALID_NCT_ID', 'Use NCT followed by exactly eight digits.')
        with self._lock:
            cached = self._cache.get(nct_id)
            if cached and self._clock() < cached[0]:
                self._cache.move_to_end(nct_id)
                return deepcopy(cached[1])
            self._cache.pop(nct_id, None)
        payload = self._fetch(nct_id)
        protocol = payload.get('protocolSection')
        identification = protocol.get('identificationModule') if isinstance(protocol, dict) else None
        if not isinstance(identification, dict) or identification.get('nctId') != nct_id:
            raise TrialLookupError('UPSTREAM_INVALID_RESPONSE', 'Registry response identity is missing or mismatched.')
        result = normalize_study(payload, nct_id, self._now().isoformat())
        with self._lock:
            self._cache[nct_id] = (self._clock() + CACHE_TTL_SECONDS, deepcopy(result))
            self._cache.move_to_end(nct_id)
            while len(self._cache) > CACHE_CAPACITY:
                self._cache.popitem(last=False)
        return result

    def _fetch(self, nct_id):
        request = Request(API_ROOT + nct_id, headers={'Accept': 'application/json'})
        for attempt in range(2):
            try:
                with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                    data = response.read(MAX_RESPONSE_BYTES + 1)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise TrialLookupError('UPSTREAM_INVALID_RESPONSE', 'Registry response exceeds the size limit.')
                payload = json.loads(data, parse_constant=_reject_constant)
                if not isinstance(payload, dict):
                    raise ValueError('Registry response must be an object')
                return payload
            except HTTPError as error:
                error.close()
                if error.code == 404:
                    raise TrialLookupError('TRIAL_NOT_FOUND', 'Registry study was not found.') from None
                if error.code >= 500 and attempt == 0:
                    continue
                raise TrialLookupError('UPSTREAM_ERROR', 'Registry service returned an error.') from None
            except (TimeoutError, URLError, OSError, HTTPException):
                if attempt == 0:
                    continue
                raise TrialLookupError('UPSTREAM_UNAVAILABLE', 'Registry service timed out or is unavailable.') from None
            except (ValueError, UnicodeError):
                raise TrialLookupError('UPSTREAM_INVALID_RESPONSE', 'Registry service returned invalid JSON.') from None
