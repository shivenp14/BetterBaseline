"""Real #68 HTTP and production browser measurements; no product edits."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import socket
import statistics
import math
import threading
import time
import subprocess
import sys
import os

from core import ROOT, canonical, environment
from http_uncached import request_payload, ROUTES, validate_response, replay_identity


class ObservedCache:
    """Delegate the real cache unchanged; record reads/writes for one serial request."""
    def __init__(self, cache):
        self.cache = cache
        self.events = []
    def get(self, key):
        value = self.cache.get(key)
        self.events.append({'operation': 'get', 'key': key, 'hit': value is not None})
        return value
    def set(self, key, value):
        self.cache.set(key, value)
        self.events.append({'operation': 'set', 'key': key})
    def clear(self):
        self.cache.clear()
    def __len__(self):
        return len(self.cache)
    def reset_observations(self, clear=False):
        if clear:
            self.clear()
        self.events.clear()
    def snapshot(self):
        return {'entries': len(self), 'events': list(self.events)}


@contextmanager
def service(port=0):
    import uvicorn
    from app.main import create_app
    app = create_app()
    observed = ObservedCache(app.state.compute_guard.cache)
    app.state.compute_guard.cache = observed
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+20
            while not server.started:
                if not thread.is_alive() or time.monotonic()>deadline:
                    raise RuntimeError('Benchmark service failed to start')
                time.sleep(.01)
            yield sock.getsockname()[1], observed
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError('Benchmark service failed to stop')


def check_cache(condition, snapshot):
    events = snapshot['events']
    reads = [e for e in events if e['operation']=='get']
    writes = [e for e in events if e['operation']=='set']
    if condition == 'uncached-grid':
        assert not events, 'Grid unexpectedly acquired cache behavior; revisit measurement labels'
    elif condition == 'cache-cold':
        assert len(reads)==1 and not reads[0]['hit'] and len(writes)==1, snapshot
        assert reads[0]['key']==writes[0]['key']
    else:
        assert len(reads)==1 and reads[0]['hit'] and not writes, snapshot


def summarize(samples):
    assert len(samples)>=30
    return {'measured_runs': len(samples), 'excluded_warmups': 3, 'raw_elapsed_ns': samples,
            'median_ms': statistics.median(samples)/1e6,
            'p95_ms': sorted(samples)[math.ceil(.95*len(samples))-1]/1e6,
            'p95_definition': 'nearest rank, ceil(0.95*runs), one-based'}


def http_measure(workload, condition, inputs, port, observed):
    body = canonical(request_payload(workload, inputs)).encode()
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    samples, snapshots, timestamps, reference = [], [], [], None
    observed.reset_observations(clear=True)
    try:
        for index in range(34): # initial priming request, three excluded warmups, 30 measured
            observed.reset_observations(clear=condition=='cache-cold')
            start = time.perf_counter_ns()
            connection.request('POST', ROUTES[workload], body, {'Content-Type':'application/json'})
            response = connection.getresponse()
            data = response.read()
            elapsed = time.perf_counter_ns()-start
            assert response.status == 200, data
            result = json.loads(data)
            validate_response(workload, inputs, result)
            if reference is None:
                reference = result
            else:
                assert replay_identity(result)==replay_identity(reference)
            snapshot = observed.snapshot()
            if index>0:
                check_cache(condition, snapshot)
            if index>=4:
                samples.append(elapsed); snapshots.append(snapshot)
                timestamps.append(result.get('computed_at',result.get('metadata',{}).get('computed_at')))
        if workload=='monte-carlo':
            assert (len(set(timestamps))==1) if condition=='cache-warm' else (len(set(timestamps))==30)
        if workload=='grid':
            assert len(set(timestamps))==30
        return {**summarize(samples), 'excluded_priming_requests':1,
                'cache_observations':snapshots, 'computed_at_samples':timestamps,
                'representative_result':reference, 'request':json.loads(body),
                'semantic_result_sha256':hashlib.sha256(replay_identity(reference).encode()).hexdigest()}
    finally:
        connection.close()


def verify_seed_identity(port, observed, inputs):
    from copy import deepcopy
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
    observations=[]
    try:
        observed.reset_observations(clear=True)
        for seed,replicates,condition in ((42,10000,'cache-cold'),(42,10000,'cache-warm'),
                                         (43,10000,'cache-cold'),(43,10000,'cache-warm'),
                                         (43,9999,'cache-cold')):
            changed=deepcopy(inputs);changed['simulation']={'seed':seed,'replicates':replicates}
            observed.reset_observations()
            connection.request('POST',ROUTES['monte-carlo'],canonical(changed),{'Content-Type':'application/json'})
            response=connection.getresponse();body=response.read();assert response.status==200,body
            result=json.loads(body);validate_response('monte-carlo',changed,result)
            snapshot=observed.snapshot();check_cache(condition,snapshot)
            observations.append({'seed':seed,'replicates':replicates,'expected_condition':condition,**snapshot})
        assert observations[0]['events'][0]['key']!=observations[2]['events'][0]['key']
        assert observations[2]['events'][0]['key']!=observations[4]['events'][0]['key']
        from app.cache import make_cache_key
        assert make_cache_key('/test','v1',inputs)!=make_cache_key('/test','v2',inputs)
        return observations
    finally:
        connection.close()


def capture_browser(port, observed):
    env = {**os.environ, 'D6_API_URL':f'http://127.0.0.1:{port}'}
    process = subprocess.Popen(['node', str(ROOT/'scripts/benchmarks/browser.mjs')],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    report = None
    try:
        for line in process.stdout:
            message = json.loads(line)
            if message['command']=='prepare':
                observed.reset_observations(clear=message['clear'])
                reply = observed.snapshot()
            elif message['command']=='snapshot':
                reply = observed.snapshot()
            elif message['command']=='report':
                report = message['value']; continue
            else:
                raise RuntimeError('Unknown browser control command')
            process.stdin.write(json.dumps(reply)+'\n');process.stdin.flush()
        assert process.wait(timeout=10)==0, 'Browser benchmark failed'
        assert report is not None
        return report
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=10)


def metadata():
    return {'measured_at_utc':datetime.now(timezone.utc).isoformat(), 'environment':environment(),
            'frontend_runtime':{'node':subprocess.check_output(['node','--version'],text=True).strip(),
                'build_id':(ROOT/'frontend/.next/BUILD_ID').read_text().strip() if (ROOT/'frontend/.next/BUILD_ID').exists() else None,
                'packages':{name:json.loads((ROOT/'frontend/node_modules'/name/'package.json').read_text())['version'] for name in ('next','react','react-dom')}},
            'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in ('backend/app','frontend/app','frontend/lib','frontend/components','scripts/benchmarks')
                for p in sorted((ROOT/folder).rglob('*')) if p.suffix in ('.py','.ts','.tsx','.mjs')},
            'instrumentation':'Benchmark-only delegating cache observer; real get/set/clear/len methods. Single serial request. Clear and inspection outside timing; no HTTP control endpoint or product-source edits.',
            'cache_key_policy':'Current design/evaluate routes use route + model_version + normalized request (effective defaults included). No separate software signature or numerical method version is embedded; fresh processes are used for each report. Grid supplies no key.',
            'timing_notice':'Local hardware/load-dependent observations; no general speedup or clinical validation claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        parser.error('Do not use -O: evidence assertions must remain enabled')
    inputs = json.loads((ROOT/'demo-data/baseline-collapse-v1/inputs.json').read_text())
    with service(8000 if args.browser else 0) as (port, observed):
        if args.browser:
            measurements = capture_browser(port, observed)
            for measurement in measurements:
                for snapshot in measurement['cache_observations']:
                    check_cache(measurement['condition'],snapshot)
                result = measurement['representative_result']
                captured = measurement['request']
                if measurement['workload']=='design':
                    witness = {**inputs,'planned_design':captured}
                else:
                    witness = captured
                if measurement['workload']=='grid':
                    from app.schemas import ScenarioGridResponse
                    from app.statistics.analytic import analytic_power
                    from app.statistics.effect import resolve_treatment_risk
                    from app.statistics.inputs import Effect, expected_retained_count
                    ScenarioGridResponse.model_validate(result)
                    assert result['fixed_enrollment']==captured['fixed_enrollment']
                    assert len(result['x_baseline'])==captured['x_baseline']['steps']
                    assert len(result['y_dropout'])==captured['y_dropout']['steps']
                    effect = Effect(**captured['planned_design']['effect'])
                    for row, dropout in enumerate(result['y_dropout']):
                        n=expected_retained_count(captured['fixed_enrollment']['control'],dropout)
                        for column, baseline in enumerate(result['x_baseline']):
                            expected=analytic_power(baseline,resolve_treatment_risk(baseline,effect),n,n,captured['planned_design']['alpha']).power
                            assert result['power'][row][column]==expected
                            assert not result['invalid_mask'][row][column]
                else:
                    validate_response(measurement['workload'],witness,result)
                timestamps=measurement['computed_at_samples']
                if measurement['workload']=='monte-carlo':
                    assert len(set(timestamps))==(1 if measurement['condition']=='cache-warm' else 30)
                if measurement['workload']=='grid':
                    assert len(set(timestamps))==30
        else:
            measurements = []
            for workload in ROUTES:
                for condition in (('uncached-grid',) if workload=='grid' else ('cache-cold','cache-warm')):
                    data=http_measure(workload,condition,inputs,port,observed)
                    measurements.append({'workload':workload,'condition':condition,**data})
                    print(workload,condition,round(data['median_ms'],3),round(data['p95_ms'],3),flush=True)
        identity_checks=verify_seed_identity(port,observed,inputs)
    for measurement in measurements:
        measurement['semantic_result_sha256']=hashlib.sha256(replay_identity(measurement['representative_result']).encode()).hexdigest()
    report = {'cache_identity_checks':identity_checks, 'benchmark_schema_version':2, **metadata(), 'frontend':args.browser,
              'scope': ('Production workspace native action through DOM result commit; excludes navigation, setup, cache reset/inspection and result validation. Includes client helper, HTTP and React DOM commit; excludes paint.' if args.browser else 'Persistent loopback HTTP POST send through complete response body receipt; excludes startup, resets/inspection, JSON parsing and validation.'),
              'measurements':measurements}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
