"""Frozen reliability-history and quality-multiplier regression tests."""
import copy
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import reconstruct_pollster_quality as quality  # noqa: E402


class PollsterQualityRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.errors = quality.load_errors()
        cls.reference = quality.load_reference()
        cls.results = quality.reconstruct(cls.errors, cls.reference)
        cls.by_key = {(r['forecast_cycle'], r['reliability_pollster']): r for r in cls.results}

    def test_eligible_error_cycle_universe_and_absolute_errors(self):
        self.assertEqual(len(self.errors), 1005)
        self.assertEqual(dict(Counter(r['cycle'] for r in self.errors)), quality.EXPECTED_ERROR_CYCLES)
        self.assertEqual(sum(r['cycle'] == 2022 for r in self.errors), 111)

    def test_full_frozen_quality_audit(self):
        audit = quality.verify_frozen(self.results, self.reference)
        self.assertEqual(audit['pollster_vintage_records'], 2729)
        self.assertEqual(audit['discrepant_records'], 0)
        self.assertLessEqual(audit['max_numeric_abs_difference'], 1e-12)

    def test_vintage_safe_prior_counts_and_global_mae(self):
        examples = [(2006, 0, None), (2008, 100, 4.109270909243599),
                    (2022, 894, 4.509642792245872), (2024, 1005, 4.457949518496256)]
        for vintage, n, mae in examples:
            with self.subTest(vintage=vintage):
                observed = [r for r in self.results if r['forecast_cycle'] == vintage]
                self.assertTrue(all(r['prior_global_n'] == n for r in observed))
                if mae is None:
                    self.assertTrue(all(r['prior_global_MAE'] is None for r in observed))
                else:
                    self.assertTrue(all(abs(r['prior_global_MAE'] - mae) < 1e-12 for r in observed))
        # In particular, the 111 eligible 2022 error rows cannot affect the 2022 forecast vintage.
        old = [r for r in self.results if r['forecast_cycle'] == 2022]
        new_errors = [e for e in self.errors if e['cycle'] < 2022]
        recomputed = quality.reconstruct(new_errors, self.reference)
        after = [r for r in recomputed if r['forecast_cycle'] == 2022]
        self.assertEqual(old, after)

    def test_no_history_and_no_clamping(self):
        no_history = [r for r in self.results if r['n_prior_polls'] == 0]
        self.assertTrue(no_history)
        self.assertTrue(all(r['raw_prior_MAE'] is None and r['quality_multiplier_p2'] == 1 for r in no_history))
        history = [r['quality_multiplier_p2'] for r in self.results if r['n_prior_polls'] > 0]
        self.assertTrue(any(q < 1 for q in history))
        self.assertTrue(any(q > 1 for q in history))
        self.assertTrue(all(r['reliability_data_through_cycle'] == '2022' for r in self.results if r['forecast_cycle'] == 2024))

    def test_fail_closed_on_reference_tamper(self):
        altered = copy.deepcopy(self.reference)
        target = next(r for r in altered if int(r['forecast_cycle']) == 2024 and int(r['n_prior_polls']) > 0)
        target['quality_multiplier_p2'] = str(float(target['quality_multiplier_p2']) + 0.01)
        with self.assertRaises(AssertionError):
            quality.verify_frozen(self.results, altered)

    def test_fail_closed_on_bad_source_error(self):
        # Perturbing the underlying prior errors changes the independently calculated history.
        altered = copy.deepcopy(self.errors)
        altered[0]['absolute_error'] += 1
        result = quality.reconstruct(altered, self.reference)
        with self.assertRaises(AssertionError):
            quality.verify_frozen(result, self.reference)


if __name__ == '__main__':
    unittest.main()
