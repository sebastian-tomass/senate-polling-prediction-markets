"""Regression and sample-guard tests for frozen 2022 hybrid development."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import fit_hybrid_2022 as development  # noqa: E402


class FrozenDevelopment2022Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = development.load_data(development.DEFAULT_DATA)
        cls.report = development.fit_hybrid(cls.rows)

    def test_sample_and_procedural_guard(self):
        self.assertEqual(len(self.rows), 34)
        self.assertEqual(len({r['polling_signal_id'] for r in self.rows}), 34)
        self.assertEqual(self.report['sample']['horizon_counts'],
                         {'60': 7, '30': 8, '14': 9, '7': 10})
        self.assertEqual(self.report['sample']['n_georgia_in_fit'], 0)
        contaminated = [dict(r) for r in self.rows]
        contaminated[0]['sample_status'] = 'POST_GENERAL_RUNOFF_ROBUSTNESS'
        with self.assertRaises(ValueError):
            self._validate_rows_through_csv(contaminated)

    @staticmethod
    def _validate_rows_through_csv(rows):
        import csv
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'contaminated.csv'
            with path.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            return development.load_data(path)

    def test_frozen_optimum_and_loss_regression(self):
        development.verify_frozen(self.report)
        self.assertLess(self.report['fit']['w_unconstrained'], 0)
        self.assertEqual(self.report['fit']['w_constrained'], 0.0)
        self.assertEqual(self.report['scores']['hybrid'], self.report['scores']['market'])

    def test_exact_horizon_scores(self):
        frozen_brier = {
            60: (0.17461373795062812, 0.10720727857142856),
            30: (0.12359104858034398, 0.11281301),
            14: (0.1099709996279145, 0.11748066333333333),
            7: (0.10859206079867507, 0.09859199700000001),
        }
        for horizon, (poll, market) in frozen_brier.items():
            with self.subTest(horizon=horizon):
                self.assertAlmostEqual(self.report['scores']['polling']['by_horizon'][str(horizon)]['brier'],
                                       poll, places=12)
                self.assertAlmostEqual(self.report['scores']['market']['by_horizon'][str(horizon)]['brier'],
                                       market, places=12)


if __name__ == '__main__':
    unittest.main()
