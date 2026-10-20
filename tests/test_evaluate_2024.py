"""Regression checks on the frozen public 2024 reproduction slice."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import evaluate_2024 as analysis  # noqa: E402


class Frozen2024Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = analysis.load_data(analysis.DEFAULT_DATA)
        cls.scores, cls.paired, cls.points = analysis.compute_losses(cls.rows)

    def test_dataset_shape_and_hybrid(self):
        self.assertEqual(len(self.rows), 60)
        self.assertEqual(len({r["state"] for r in self.rows}), 18)
        self.assertEqual(self.scores["hybrid"], self.scores["market"])
        self.assertEqual(sum(r["source_data_anomaly_present"] == "true" for r in self.rows), 2)

    def test_frozen_horizon_scores(self):
        expected = {
            60: (0.11809273637633573, 0.10454791666666667),
            30: (0.07711028641276763, 0.0674800294117647),
            14: (0.08013402051458364, 0.06594951666666667),
            7: (0.07459900329087878, 0.0664348125),
        }
        for horizon, (poll, market) in expected.items():
            with self.subTest(horizon=horizon):
                self.assertAlmostEqual(self.scores["polling"]["by_horizon"][str(horizon)]["brier"], poll, places=12)
                self.assertAlmostEqual(self.scores["market"]["by_horizon"][str(horizon)]["brier"], market, places=12)

    def test_exact_bootstrap_regression(self):
        bootstrap = analysis.race_bootstrap(self.rows, self.paired)
        analysis.assert_frozen(self.scores, self.points, bootstrap)
        self.assertEqual(bootstrap["valid_replicates"], 50_000)
        self.assertEqual(bootstrap["empty_horizon_replicates"], 0)
        self.assertEqual(bootstrap["discarded_or_redrawn"], 0)


if __name__ == "__main__":
    unittest.main()
