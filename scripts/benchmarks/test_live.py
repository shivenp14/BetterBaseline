"""Audit real cache/render evidence; reject false conditions and corrupted values."""
import json
import hashlib
import unittest
from core import ROOT
from live import check_cache, summarize
from http_uncached import replay_identity, validate_response

class LiveEvidenceTests(unittest.TestCase):
    def test_false_cache_labels_are_rejected(self):
        miss={'operation':'get','key':'k','hit':False}
        hit={'operation':'get','key':'k','hit':True}
        write={'operation':'set','key':'k'}
        for condition,events in [('cache-cold',[hit]),('cache-warm',[miss,write]),('uncached-grid',[hit])]:
            with self.assertRaises(AssertionError):
                check_cache(condition,{'events':events})
        check_cache('cache-cold',{'events':[miss,write]})
        check_cache('cache-warm',{'events':[hit]})
        check_cache('uncached-grid',{'events':[]})

    def test_retained_live_reports(self):
        paths=list((ROOT/'scripts/benchmarks/reports/live').glob('*.json'))
        self.assertEqual(len(paths),2)
        for path in paths:
            report=json.loads(path.read_text())
            self.assertEqual(len(report['measurements']),5)
            for filename in ('scripts/benchmarks/live.py','scripts/benchmarks/browser.mjs'):
                self.assertEqual(report['source_sha256'][filename],hashlib.sha256((ROOT/filename).read_bytes()).hexdigest())
            for entry in report['measurements']:
                self.assertEqual(entry['semantic_result_sha256'],hashlib.sha256(replay_identity(entry['representative_result']).encode()).hexdigest())
                if not report['frontend']:
                    inputs=json.loads((ROOT/'demo-data/baseline-collapse-v1/inputs.json').read_text())
                    validate_response(entry['workload'],inputs,entry['representative_result'])
                summary=summarize(entry['raw_elapsed_ns'])
                for key,value in summary.items():
                    self.assertEqual(entry[key],value)
                self.assertEqual(len(entry['cache_observations']),30)
                for observation in entry['cache_observations']:
                    check_cache(entry['condition'],observation)
                if entry['workload']=='monte-carlo':
                    expected=1 if entry['condition']=='cache-warm' else 30
                    self.assertEqual(len(set(entry['computed_at_samples'])),expected)
                if entry['workload']=='grid':
                    self.assertEqual(len(set(entry['computed_at_samples'])),30)
            witnesses=report['cache_identity_checks']
            self.assertEqual(len(witnesses),5)
            for witness in witnesses:
                check_cache(witness['expected_condition'],witness)
            self.assertNotEqual(witnesses[0]['events'][0]['key'],witnesses[2]['events'][0]['key'])
            self.assertNotEqual(witnesses[2]['events'][0]['key'],witnesses[4]['events'][0]['key'])

if __name__=='__main__':
    unittest.main()
