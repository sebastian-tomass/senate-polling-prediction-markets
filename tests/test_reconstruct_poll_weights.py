"""Regression tests for the frozen poll-usage construction and aggregations."""
import copy
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import reconstruct_poll_weights as rw  # noqa: E402
from reconstruct_pollster_quality import load_errors,load_reference,reconstruct  # noqa: E402


class PollLevelReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source,cls.mapping,cls.references=rw.load_inputs()
        cls.quality=reconstruct(load_errors(),load_reference())
        cls.rows=rw.make_row_weights(cls.source,cls.mapping,cls.quality)
        cls.signals,cls.differences=rw.aggregate(cls.rows,cls.references)

    def test_exact_usage_and_signal_universe(self):
        self.assertEqual(len(self.rows),7346)
        self.assertEqual(len(self.signals),629)
        self.assertEqual(Counter(r['cycle'] for r in self.signals),
                         {2006:33,2008:69,2010:70,2012:79,2014:98,
                          2016:69,2018:70,2020:43,2022:38,2024:60})
        self.assertEqual(Counter(int(r['cycle']) for r in self.rows),rw.EXPECTED_ROWS)

    def test_exact_full_precision_row_weights(self):
        for r in self.rows:
            with self.subTest(race=r['polling_signal_id'],source=r['poll_source_identifier']):
                self.assertLess(abs(r['v1_poll_weight']-float(r['frozen_v1_poll_weight'])),1e-10)
                self.assertLess(abs(r['v2_p2_poll_weight']-float(r['frozen_v2_p2_poll_weight'])),1e-10)
                self.assertLess(abs(r['v2_p2_poll_weight']-r['v1_poll_weight']*r['quality_multiplier_p2']),1e-14)

    def test_exact_signal_reconstruction(self):
        self.assertLess(max(self.differences.values()),1e-10)
        self.assertEqual(sum(int(r['poll_count']) for r in self.signals),7346)

    def test_repeat_bin_rule_original_canonical(self):
        self.assertEqual(Counter(r['repeat_bin_count'] for r in self.rows),{1:7074,2:260,3:12})
        for r in self.rows:
            self.assertEqual(r['w_repeat'],1/r['repeat_bin_count'])
        # The later reliability identity must never determine repeat grouping.
        resolved=next(r for r in self.rows if r['polling_signal_id']=='2006-maryland-30d'
                      and r['v1_canonical_pollster']=='SurveyUSA' and r['repeat_bin_count']==2)
        self.assertEqual(resolved['repeat_bin_count'],2)
        self.assertEqual(resolved['w_repeat'],0.5)

    def test_sample_fallback_and_cap(self):
        fallback=[r for r in self.rows if r['sample_size']=='']
        capped=[r for r in self.rows if r['sample_size'] and float(r['sample_size'])>5000]
        self.assertGreater(len(fallback),0)
        for r in fallback:self.assertEqual(r['w_sample'],1)
        for r in capped:self.assertAlmostEqual(r['w_sample'],math.sqrt(5000/600),places=14)
        self.assertTrue(all(r['sample_fallback_used'] for r in fallback))

    def test_anomaly_preservation_and_no_repair(self):
        a=[r for r in self.rows if r['source_data_anomaly']=='True']
        self.assertEqual({r['polling_signal_id'] for r in a},rw.ANOMALOUS_SIGNALS)
        self.assertEqual(len(a),2)
        self.assertTrue(all(int(r['source_cycle_row_number'])==5 for r in a))
        self.assertEqual(Counter(int(r['cycle']) for r in self.rows if r['source_date_reversal_detected']),
                         {2016:3,2020:3,2022:2,2024:2})
        self.assertFalse(any(r['polling_signal_id']=='2024-arizona-30d' and r['source_data_anomaly']=='True' for r in self.rows))

    def test_fail_closed_quality_and_identity_mapping(self):
        tainted=[dict(r) for r in self.source]
        target=next(r for r in tainted if int(r['cycle'])==2024 and r['identity_status']=='MATCHED_HISTORY')
        target['reliability_pollster']='Nonexistent pollster identity'
        with self.assertRaises(ValueError):
            rw.make_row_weights(tainted,self.mapping,self.quality)
        dropped=dict(self.mapping)
        dropped.pop((2022,next(r['raw_pollster_name'] for r in self.source if int(r['cycle'])==2022)))
        with self.assertRaises(ValueError):
            rw.make_row_weights(self.source,dropped,self.quality)

    def test_fail_closed_frozen_row_comparison(self):
        tainted=[dict(r) for r in self.source]
        tainted[100]['frozen_v1_poll_weight']=str(float(tainted[100]['frozen_v1_poll_weight'])+.001)
        with self.assertRaises(AssertionError):
            rw.make_row_weights(tainted,self.mapping,self.quality)


if __name__=='__main__':unittest.main()
