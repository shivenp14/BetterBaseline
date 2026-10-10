"""Run an authenticated synthetic upload against an already deployed API/worker."""

import json
import os
import time
from urllib.parse import urlsplit

import httpx

STUDY = '30f04fb1-10cd-5674-88a0-2a6b4962a848'


def smoke(base_url, token, timeout_seconds=180):
    origin = urlsplit(base_url)
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('TRIALSYNC_API_URL must be an HTTPS origin')
    if not token or any(c.isspace() for c in token):
        raise ValueError('TRIALSYNC_ACCESS_TOKEN is required')
    project_origin = urlsplit(os.environ['SUPABASE_URL'])
    if project_origin.scheme != 'https' or not project_origin.hostname:
        raise ValueError('SUPABASE_URL must be configured before smoke uploads')
    with httpx.Client(base_url=base_url.rstrip('/'), timeout=15, follow_redirects=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, headers={'Authorization': f'Bearer {token}'}, **kwargs)
            response.raise_for_status()
            return response.json()
        client.get('/ready').raise_for_status()
        assert client.get(f'/api/studies/{STUDY}/graph').status_code == 401
        artifacts = request('GET', f'/api/studies/{STUDY}/artifacts')['items']
        protocol = next(item for item in artifacts if item['kind'] == 'protocol')
        payload = json.dumps({'facts': [{'logical_key': 'endpoint.week', 'label': 'Primary endpoint week',
            'value': 36, 'unit': 'weeks', 'locator': 'Synthetic protocol smoke §1',
            'quote': 'Synthetic primary endpoint occurs at week 36.'}]}).encode()
        receipt = request('POST', f"/api/artifacts/{protocol['id']}/versions",
                          files={'file': ('hosted-smoke.json', payload, 'application/json')})
        deadline = time.monotonic() + timeout_seconds
        while True:
            job = request('GET', f"/api/jobs/{receipt['job']['id']}")
            if job['status'] == 'succeeded':
                break
            if job['status'] == 'failed' or time.monotonic() >= deadline:
                raise RuntimeError('Hosted worker did not complete the smoke job')
            time.sleep(1)
        source = request('GET', f"/api/versions/{receipt['version']['id']}/source")['url']
        # The source is a short-lived Supabase capability; never forward the user JWT there.
        source_origin = urlsplit(source)
        if source_origin.scheme != 'https' or source_origin.netloc != project_origin.netloc or not source_origin.path.startswith('/storage/v1/object/sign/'):
            raise ValueError('Unexpected private source origin')
        response = client.get(source)
        response.raise_for_status()
        assert response.content == payload
        print(f"Hosted upload succeeded: version={receipt['version']['id']} job={job['id']}")


if __name__ == '__main__':
    try:
        smoke(os.environ['TRIALSYNC_API_URL'], os.environ['TRIALSYNC_ACCESS_TOKEN'])
    except Exception:
        raise SystemExit('Hosted smoke failed; check auth membership, API/worker, and private storage. Credentials and signed URLs omitted.') from None
