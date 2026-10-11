"""Synthetic API-v2-shaped fixtures and mocked transport; no live network tests."""
from copy import deepcopy
from datetime import datetime, timezone
import io
from http.client import BadStatusLine, HTTPResponse
import json
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from app.data.clinicaltrials import (
    API_ROOT, CACHE_CAPACITY, CACHE_TTL_SECONDS, MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS, ClinicalTrialsClient, TrialLookupError, _NoRedirect,
)


class RegisteredTrialTests(unittest.TestCase):
    def test_registered_route_returns_metadata_without_planning_assumptions(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.routers.trials import get_trial_client
        client = ClinicalTrialsClient(opener=Mock(open=Mock(return_value=response())))
        app = create_app()
        app.dependency_overrides[get_trial_client] = lambda: client
        with TestClient(app) as http:
            result = http.get('/api/v1/trials/' + NCT)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.json()['planned_control_event_rate'])
        self.assertIsNone(result.json()['planned_effect'])
        self.assertEqual(result.json()['nct_id'], NCT)

    def test_failure_is_explicit_and_cannot_block_calculations(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.routers.trials import get_trial_client
        app = create_app()
        opener = Mock()
        opener.open.side_effect = URLError('offline')
        app.dependency_overrides[get_trial_client] = lambda: ClinicalTrialsClient(opener=opener)
        with TestClient(app) as http:
            malformed = http.get('/api/v1/trials/not-an-nct')
            self.assertEqual(malformed.status_code, 422)
            self.assertEqual(malformed.json()['error']['code'], 'INVALID_NCT_ID')
            opener.open.assert_not_called()
            failed = http.get('/api/v1/trials/' + NCT)
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.json()['error']['code'], 'UPSTREAM_UNAVAILABLE')
            self.assertEqual(opener.open.call_count, 2)
            # Actual preset and manual planning endpoints still execute, rather
            # than falling back to fabricated registry assumptions.
            from pathlib import Path
            root = Path(__file__).resolve().parents[2]
            planned = json.loads((root/'demo-data/baseline-collapse-v1/inputs.json').read_text())['planned_design']
            for risk in (.20, .23):
                result = http.post('/api/v1/design/calculate', json={**planned, 'control_event_rate': risk})
                self.assertEqual(result.status_code, 200)
                self.assertGreater(result.json()['enrolled_n']['control'], 0)
            self.assertEqual(opener.open.call_count, 2)

NCT = 'NCT01234567'
FIXTURE = {
    'protocolSection': {
        'identificationModule': {'nctId': NCT, 'briefTitle': 'Synthetic trial'},
        'designModule': {'studyType': 'INTERVENTIONAL', 'phases': ['PHASE3'],
                         'designInfo': {'allocation': 'RANDOMIZED'}},
        'outcomesModule': {'primaryOutcomes': [{'measure': 'Synthetic endpoint', 'timeFrame': '12 weeks'}]},
        'armsInterventionsModule': {'armGroups': [{'label': 'Control', 'type': 'PLACEBO_COMPARATOR',
                                                 'interventionNames': ['Drug: placebo']}]},
        'eligibilityModule': {'sex': 'ALL', 'minimumAge': '18 Years'},
    },
    # Deliberately tempting observed values: never used as planning assumptions.
    'resultsSection': {'control_event_rate': .4, 'relative_risk': .7},
}


def response(payload=FIXTURE):
    return io.BytesIO(json.dumps(payload).encode())


def truncated_chunked_response():
    # Exercise http.client's real chunk parser rather than a BytesIO read that
    # cannot raise the protocol errors returned by urllib's HTTP transport.
    class Socket:
        def makefile(self, mode):
            return io.BytesIO(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n20\r\n{}')
    result = HTTPResponse(Socket())
    result.begin()
    return result


class TrialAdapterTests(unittest.TestCase):
    def client(self, *responses):
        opener = Mock()
        opener.open.side_effect = list(responses) or [response()]
        client = ClinicalTrialsClient(opener=opener, now=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc))
        return client, opener

    def assert_error(self, client, code, nct=NCT):
        with self.assertRaises(TrialLookupError) as caught:
            client.lookup(nct)
        self.assertEqual(caught.exception.code, code)

    def test_malformed_ids_make_no_request(self):
        client, opener = self.client()
        for value in ('nct01234567', ' NCT01234567', NCT+'\n', 'NCT123', 'NCT１２３４５６７８',
                      'https://evil.example', NCT+'/../x', None, True, 123):
            self.assert_error(client, 'INVALID_NCT_ID', value)
        opener.open.assert_not_called()

    def test_fixed_url_timeout_provenance_and_null_assumptions(self):
        client, opener = self.client()
        result = client.lookup(NCT)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, API_ROOT + NCT)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], TIMEOUT_SECONDS)
        self.assertEqual(result['title'], 'Synthetic trial')
        self.assertEqual(result['phases'], ['PHASE3'])
        self.assertEqual(result['arms'][0]['label'], 'Control')
        self.assertEqual(result['eligibility']['minimumAge'], '18 Years')
        self.assertIsNone(result['planned_control_event_rate'])
        self.assertIsNone(result['planned_effect'])
        self.assertEqual(result['planning_assumptions_source'], 'unavailable')
        self.assertEqual(result['provenance']['source'], 'clinicaltrials_registry')
        self.assertEqual(result['provenance']['source_url'], result['source_url'])
        self.assertEqual(result['retrieved_at'], '2026-10-11T00:00:00+00:00')
        json.dumps(result, allow_nan=False)

    def test_absent_optional_modules_and_no_results(self):
        payload = {'protocolSection': {'identificationModule': {'nctId': NCT}}}
        client, _ = self.client(response(payload))
        result = client.lookup(NCT)
        self.assertIsNone(result['title'])
        self.assertEqual(result['primary_outcomes'], [])
        self.assertEqual(result['arms'], [])
        self.assertIsNone(result['planned_effect'])

    def test_malformed_optional_modules_are_safe(self):
        payload = deepcopy(FIXTURE)
        for key in ('designModule', 'outcomesModule', 'armsInterventionsModule', 'eligibilityModule'):
            payload['protocolSection'][key] = ['not a mapping']
        payload['protocolSection']['identificationModule']['briefTitle'] = 7
        client, _ = self.client(response(payload))
        result = client.lookup(NCT)
        self.assertIsNone(result['title'])
        self.assertEqual(result['phases'], [])
        self.assertEqual(result['primary_outcomes'], [])
        json.dumps(result, allow_nan=False)

    def test_malformed_optional_list_items_are_filtered(self):
        payload = deepcopy(FIXTURE)
        payload['protocolSection']['designModule']['phases'] = ['PHASE3', 5, None]
        payload['protocolSection']['outcomesModule']['primaryOutcomes'] = [None, {'measure': 12}]
        payload['protocolSection']['armsInterventionsModule']['armGroups'] = [False, {'interventionNames': [4, 'Drug: A']}]
        client, _ = self.client(response(payload))
        result = client.lookup(NCT)
        self.assertEqual(result['phases'], ['PHASE3'])
        self.assertEqual(result['primary_outcomes'], [{'measure': None, 'description': None, 'timeFrame': None}])
        self.assertEqual(result['arms'][0]['intervention_names'], ['Drug: A'])

    def test_unknown_not_retried_or_cached(self):
        client, opener = self.client(HTTPError(API_ROOT+NCT, 404, '', {}, None), response())
        self.assert_error(client, 'TRIAL_NOT_FOUND')
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(client.lookup(NCT)['nct_id'], NCT)
        self.assertEqual(opener.open.call_count, 2)

    def test_timeout_and_transport_errors_have_bounded_retry(self):
        for error in (TimeoutError(), URLError('offline')):
            client, opener = self.client(error, error)
            self.assert_error(client, 'UPSTREAM_UNAVAILABLE')
            self.assertEqual(opener.open.call_count, 2)

    def test_5xx_retry_can_recover(self):
        client, opener = self.client(HTTPError(API_ROOT+NCT, 503, '', {}, None), response())
        self.assertEqual(client.lookup(NCT)['nct_id'], NCT)
        self.assertEqual(opener.open.call_count, 2)

    def test_truncated_chunked_response_retries_and_recovers(self):
        broken = truncated_chunked_response()
        client, opener = self.client(broken, response())
        self.assertEqual(client.lookup(NCT)['nct_id'], NCT)
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(broken.isclosed())

    def test_protocol_status_failure_has_bounded_retry(self):
        client, opener = self.client(BadStatusLine('broken status'), BadStatusLine('broken status'))
        self.assert_error(client, 'UPSTREAM_UNAVAILABLE')
        self.assertEqual(opener.open.call_count, 2)

    def test_truncated_response_exhaustion_is_stable_at_registered_route(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.routers.trials import get_trial_client
        client, opener = self.client(truncated_chunked_response(), truncated_chunked_response())
        app = create_app()
        app.dependency_overrides[get_trial_client] = lambda: client
        with TestClient(app, raise_server_exceptions=False) as http:
            result = http.get('/api/v1/trials/' + NCT)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()['error']['code'], 'UPSTREAM_UNAVAILABLE')
        self.assertTrue(result.json()['error']['recoverable'])
        self.assertEqual(opener.open.call_count, 2)

    def test_5xx_exhaustion_and_other_statuses_are_explicit(self):
        for code, count in ((500, 2), (429, 1), (403, 1), (302, 1)):
            error = HTTPError(API_ROOT+NCT, code, '', {}, None)
            client, opener = self.client(*([error]*count))
            self.assert_error(client, 'UPSTREAM_ERROR')
            self.assertEqual(opener.open.call_count, count)

    def test_redirect_handler_refuses_all_redirects(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_bad_json_size_and_identity_are_explicit_without_retry(self):
        for data in (b'bad', b'[]', b'{"x":NaN}', b'x'*(MAX_RESPONSE_BYTES+1),
                     json.dumps({}).encode(),
                     json.dumps({'protocolSection': {'identificationModule': {'nctId': 'NCT99999999'}}}).encode()):
            client, opener = self.client(io.BytesIO(data))
            self.assert_error(client, 'UPSTREAM_INVALID_RESPONSE')
            self.assertEqual(opener.open.call_count, 1)

    def test_cache_preserves_retrieval_time_and_defends_mutation(self):
        client, opener = self.client()
        first = client.lookup(NCT)
        first['arms'][0]['label'] = 'mutated'
        first['planned_control_event_rate'] = .99
        second = client.lookup(NCT)
        self.assertEqual(second['arms'][0]['label'], 'Control')
        self.assertIsNone(second['planned_control_event_rate'])
        self.assertEqual(second['retrieved_at'], first['retrieved_at'])
        self.assertEqual(opener.open.call_count, 1)

    def test_ttl_expiry_fetches_again(self):
        client, opener = self.client(response(), response())
        current = [0]
        client._clock = lambda: current[0]
        client.lookup(NCT)
        current[0] = CACHE_TTL_SECONDS
        client.lookup(NCT)
        self.assertEqual(opener.open.call_count, 2)

    def test_lru_capacity_is_bounded(self):
        client, opener = self.client()
        opener.open.side_effect = lambda req, **kw: response({'protocolSection': {
            'identificationModule': {'nctId': req.full_url.rsplit('/', 1)[1]}}})
        for number in range(CACHE_CAPACITY+1):
            client.lookup(f'NCT{number:08d}')
        self.assertEqual(len(client._cache), CACHE_CAPACITY)
        self.assertNotIn('NCT00000000', client._cache)
        client.lookup('NCT00000001')
        client.lookup('NCT99999999')
        self.assertIn('NCT00000001', client._cache)
        self.assertNotIn('NCT00000002', client._cache)


if __name__ == '__main__':
    unittest.main()
