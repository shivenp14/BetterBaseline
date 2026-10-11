"""Opt-in local real HTTP benchmark before #68; refuses the completed cache wrapper."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time

from core import ROOT, PRESETS, canonical, environment, prepare

# Exact pass-through scaffold from main c7fe68d. Cache timings require #116.
SCAFFOLD_SHA256 = 'aba783fe64bbd8ff93bd2dd5206a979c5cabb98db2e2df7ebb5658a726a86150'
ROUTES = {'design': '/api/v1/design/calculate', 'grid': '/api/v1/scenarios/grid',
          'monte-carlo': '/api/v1/scenarios/evaluate'}


def ensure_uncached_service():
    if not __debug__:
        raise ValueError('Run without -O: numerical assertions must remain enabled.')
    actual = hashlib.sha256((ROOT / 'backend/app/services/compute.py').read_bytes()).hexdigest()
    if actual != SCAFFOLD_SHA256:
        raise ValueError('Compute wrapper changed: stop and adapt cache benchmarks after #116; no uncached label is inferred.')


def request_payload(workload, inputs):
    if workload == 'design':
        return inputs['planned_design']
    if workload == 'grid':
        return {'planned_design': inputs['planned_design'], 'fixed_enrollment': inputs['fixed_enrollment'],
                'selected_scenario': inputs['stress_scenario'],
                'x_baseline': {'min': .05, 'max': .35, 'steps': 31},
                'y_dropout': {'min': 0, 'max': .2, 'steps': 21}}
    return inputs


def replay_identity(result):
    # Only the documented generation timestamp varies; hashes and all numeric,
    # method, seed, warning, source and software fields still must replay.
    copy = json.loads(canonical(result))
    if 'metadata' in copy:
        copy['metadata'].pop('computed_at', None)
    copy.pop('computed_at', None)
    return canonical(copy)


def validate_response(workload, inputs, result):
    from app.schemas import DesignCalculateResponse, ScenarioGridResponse
    from app.routers.scenarios import EvaluationResponse
    from app.statistics.analytic import analytic_power
    from app.statistics.effect import resolve_treatment_risk
    from app.statistics.inputs import Effect, expected_retained_count
    model = {'design': DesignCalculateResponse, 'grid': ScenarioGridResponse,
             'monte-carlo': EvaluationResponse}[workload]
    model.model_validate(result)
    if workload == 'design':
        expected = prepare('design', inputs)()
        assert result['evaluable_n'] == dict.fromkeys(('control', 'treatment'), expected['evaluable_per_arm'])
        assert result['enrolled_n'] == dict.fromkeys(('control', 'treatment'), expected['enrolled_per_arm'])
        assert result['nominal_power_evaluable'] == expected['achieved_power']
        return
    plan = inputs['planned_design']
    stress = inputs['stress_scenario']
    effect = Effect(**(stress['effect_override'] or plan['effect']))
    if workload == 'monte-carlo':
        assert result['metadata']['fixed_enrollment'] == inputs['fixed_enrollment']
        expected = prepare('monte-carlo', inputs)()
        for key, value in expected.items():
            if key == 'warnings':
                assert all(warning in result['warnings'] for warning in value)
            else:
                assert result['monte_carlo'][key] == value, key
        n = expected_retained_count(inputs['fixed_enrollment']['control'], stress['dropout']['control'])
        expected_power = analytic_power(stress['control_event_rate'], resolve_treatment_risk(stress['control_event_rate'], effect), n, n, plan['alpha']).power
        assert result['analytic']['conditional_power_approx'] == expected_power
        return
    assert result['fixed_enrollment'] == inputs['fixed_enrollment']
    assert len(result['x_baseline']) == 31 and len(result['y_dropout']) == 21
    for field in ('power', 'invalid_mask', 'below_target'):
        assert len(result[field]) == 21 and all(len(row) == 31 for row in result[field]), field
    assert all(math.isclose(value, (5+i)/100, abs_tol=1e-14) for i, value in enumerate(result['x_baseline']))
    assert all(math.isclose(value, i/100, abs_tol=1e-14) for i, value in enumerate(result['y_dropout']))
    valid = []
    for row, dropout in enumerate(result['y_dropout']):
        n = expected_retained_count(inputs['fixed_enrollment']['control'], dropout)
        for column, baseline in enumerate(result['x_baseline']):
            expected = analytic_power(baseline, resolve_treatment_risk(baseline, effect), n, n, plan['alpha']).power
            assert not result['invalid_mask'][row][column]
            assert result['power'][row][column] == expected
            assert result['below_target'][row][column] == (expected < plan['target_power'])
            valid.append(expected)
    assert result['worst_case_power'] == min(valid) and result['invalid_cell_count'] == 0
    for point, baseline in zip(result['power_curve'], result['x_baseline']):
        n = expected_retained_count(inputs['fixed_enrollment']['control'], stress['dropout']['control'])
        expected = analytic_power(baseline, resolve_treatment_risk(baseline, effect), n, n, plan['alpha']).power
        assert point['p_control'] == baseline
        assert point['power'] == expected
    assert len(result['power_curve']) == 31


@contextmanager
def local_server():
    # Each command owns a new single-worker loopback service from this checkout.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                    '--host', '127.0.0.1', '--port', str(port), '--workers', '1',
                                    '--no-access-log'], cwd=ROOT / 'backend', stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    raise RuntimeError('Local service did not start: ' + log.read().decode(errors='replace'))
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
                try:
                    connection.request('GET', '/healthz')
                    response = connection.getresponse()
                    body = response.read()
                    if response.status == 200 and json.loads(body)['model_version'] == 'binary-v1':
                        break
                except (OSError, http.client.HTTPException):
                    pass
                finally:
                    connection.close()
                time.sleep(.05)
            yield port
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def benchmark(workload, inputs, port, runs=30, warmups=3):
    if not 30 <= runs <= 10000 or not 1 <= warmups <= 100:
        raise ValueError('runs must be 30..10000 and warmups 1..100')
    body = canonical(request_payload(workload, inputs)).encode()
    samples, timestamps, reference = [], [], None
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    try:
        for index in range(warmups + runs):
            start = time.perf_counter_ns()
            connection.request('POST', ROUTES[workload], body, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = response.read()
            elapsed = time.perf_counter_ns() - start
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status}: {data.decode(errors="replace")}')
            result = json.loads(data)
            validate_response(workload, inputs, result)
            identity = replay_identity(result)
            if reference is None:
                reference, expected_identity = result, identity
            elif identity != expected_identity:
                raise RuntimeError('Identical requests produced different semantic results')
            if index >= warmups:
                samples.append(elapsed)
                timestamps.append(result.get('computed_at', result.get('metadata', {}).get('computed_at')))
    finally:
        connection.close()
    return {'measured_runs': runs, 'excluded_warmups': warmups, 'raw_elapsed_ns': samples,
            'median_ms': statistics.median(samples)/1e6,
            'p95_ms': sorted(samples)[math.ceil(.95*runs)-1]/1e6,
            'p95_definition': 'nearest rank, ceil(0.95*runs), one-based',
            'representative_result': reference,
            'result_sha256': hashlib.sha256(canonical(reference).encode()).hexdigest(),
            'semantic_result_sha256': hashlib.sha256(expected_identity.encode()).hexdigest(),
            'ignored_replay_fields': ['metadata.computed_at'] if 'metadata' in reference else (['computed_at'] if 'computed_at' in reference else []),
            'measured_computed_at': timestamps, 'identical_semantic_results': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workload', choices=tuple(ROUTES), required=True)
    parser.add_argument('--preset', choices=PRESETS, default=PRESETS[0])
    parser.add_argument('--runs', type=int, default=30)
    parser.add_argument('--warmups', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        ensure_uncached_service()
        directory = ROOT / 'demo-data' / args.preset
        inputs = json.loads((directory / 'inputs.json').read_text())
        manifest = json.loads((directory / 'manifest.json').read_text())
        inputs_hash = 'sha256:' + hashlib.sha256(canonical(inputs).encode()).hexdigest()
        if inputs_hash != manifest['inputs_hash']:
            raise ValueError('D1 fixture hash mismatch')
        with local_server() as port:
            measurement = benchmark(args.workload, inputs, port, args.runs, args.warmups)
        parameters = {'route': ROUTES[args.workload], 'request': request_payload(args.workload, inputs)}
        report = {'benchmark_schema_version': 1, 'measured_at_utc': datetime.now(timezone.utc).isoformat(),
                  'workload': args.workload, 'preset_id': args.preset, 'preset_version': manifest['preset_version'],
                  'inputs': inputs, 'inputs_hash': inputs_hash, 'provenance': manifest['provenance'],
                  'computation_parameters': parameters,
                  'computation_sha256': hashlib.sha256(canonical(parameters).encode()).hexdigest(),
                  'scope': 'loopback HTTP request send through complete response body receipt; includes server parsing/validation/computation/serialization; excludes client JSON decoding, invariant checks, service startup, fixture loading, reporting and frontend rendering',
                  'cache_condition': 'uncached pass-through #64 compute scaffold; warm process; NOT #68 cold/warm cache measurement',
                  'server': {'workers': 1, 'concurrent_requests': 1, 'owned_fresh_process': True,
                             'connection': 'persistent HTTP/1.1; initial connection in excluded warmups'},
                  'environment': environment(),
                  'service_source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend/app').rglob('*.py'))},
                  'http_harness_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'numerical_invariants_checked': True, 'measurement': measurement,
                  'timing_notice': 'Hardware/load-dependent local measurements; no speedup or clinical validation claim.'}
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        print(f"{args.workload}: median {measurement['median_ms']:.3f} ms; p95 {measurement['p95_ms']:.3f} ms; {args.output}")
    except (ValueError, OSError, RuntimeError, AssertionError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
