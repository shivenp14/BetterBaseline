"""Audit real HTTP evidence and reject mutations; no timing thresholds."""
from copy import deepcopy
import hashlib
import json
import math
import statistics
import unittest
from unittest.mock import patch

from core import ROOT, canonical
from http_uncached import ensure_uncached_service, replay_identity, validate_response


class HttpEvidenceTests(unittest.TestCase):
    def reports(self):
        return [json.loads(p.read_text()) for p in sorted((ROOT/'scripts/benchmarks/reports/http').glob('*.json'))]

    def test_raw_evidence_and_actual_api_results(self):
        reports = self.reports()
        self.assertEqual({r['workload'] for r in reports}, {'design', 'grid', 'monte-carlo'})
        for report in reports:
            with self.subTest(workload=report['workload']):
                measurement = report['measurement']
                samples = measurement['raw_elapsed_ns']
                self.assertGreaterEqual(len(samples), 30)
                self.assertEqual(len(samples), measurement['measured_runs'])
                self.assertTrue(all(type(v) is int and v > 0 for v in samples))
                self.assertEqual(measurement['median_ms'], statistics.median(samples)/1e6)
                self.assertEqual(measurement['p95_ms'], sorted(samples)[math.ceil(.95*len(samples))-1]/1e6)
                result = measurement['representative_result']
                self.assertEqual(measurement['result_sha256'], hashlib.sha256(canonical(result).encode()).hexdigest())
                self.assertEqual(measurement['semantic_result_sha256'], hashlib.sha256(replay_identity(result).encode()).hexdigest())
                self.assertEqual(report['computation_sha256'], hashlib.sha256(canonical(report['computation_parameters']).encode()).hexdigest())
                self.assertEqual(report['http_harness_source_sha256'], hashlib.sha256((ROOT/'scripts/benchmarks/http_uncached.py').read_bytes()).hexdigest())
                validate_response(report['workload'], report['inputs'], result)
                if report['workload'] != 'design':
                    self.assertEqual(len(set(measurement['measured_computed_at'])), len(samples))

    def test_timestamp_only_replay_exception(self):
        for report in self.reports():
            result = report['measurement']['representative_result']
            changed = deepcopy(result)
            if report['workload'] == 'design':
                changed['inputs_hash'] += 'changed'
                self.assertNotEqual(replay_identity(result), replay_identity(changed))
                continue
            if 'metadata' in changed:
                changed['metadata']['computed_at'] = 'new time'
                hash_owner = changed['metadata']
            else:
                changed['computed_at'] = 'new time'
                hash_owner = changed
            self.assertEqual(replay_identity(result), replay_identity(changed))
            hash_owner['inputs_hash'] += 'changed'
            self.assertNotEqual(replay_identity(result), replay_identity(changed))

    def test_numerical_mutations_rejected(self):
        for report in self.reports():
            result = deepcopy(report['measurement']['representative_result'])
            workload = report['workload']
            if workload == 'design':
                result['nominal_power_evaluable'] = .1
            elif workload == 'grid':
                result['power'][0][0] = .1
            else:
                result['monte_carlo']['seed'] = 43
            with self.assertRaises((AssertionError, ValueError)):
                validate_response(workload, report['inputs'], result)

    def test_changed_compute_wrapper_stops_before_server_or_measurement(self):
        with patch('http_uncached.Path.read_bytes', return_value=b'completed cache implementation'):
            with self.assertRaisesRegex(ValueError, '#116'):
                ensure_uncached_service()
        

if __name__ == '__main__':
    unittest.main()
