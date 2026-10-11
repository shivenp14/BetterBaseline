"""Optional registry metadata lookup; never supplies clinical planning inputs."""
from fastapi import APIRouter, Depends

from ..data.clinicaltrials import ClinicalTrialsClient, TrialLookupError
from ..errors import make_error_response
from ..schemas import ErrorEnvelope

router = APIRouter(prefix="/api/v1/trials", tags=["trials"])
_client = ClinicalTrialsClient()


def get_trial_client() -> ClinicalTrialsClient:
    return _client


@router.get("/{nct_id}", responses={code: {"model": ErrorEnvelope}
                                  for code in (404, 422, 502, 503)})
def lookup_trial(nct_id: str, client: ClinicalTrialsClient = Depends(get_trial_client)):
    """Return cached metadata with null, unverified planning assumptions.

    Synchronous bounded transport runs in FastAPI's worker pool; no lookup is
    performed at startup or by calculate/evaluate/grid endpoints.
    """
    try:
        return client.lookup(nct_id)
    except TrialLookupError as error:
        status = {"INVALID_NCT_ID": 422, "TRIAL_NOT_FOUND": 404,
                  "UPSTREAM_UNAVAILABLE": 503}.get(error.code, 502)
        return make_error_response(status_code=status, code=error.code,
                                   message=str(error), recoverable=status >= 500)
