"""Tests for the frozen 2006–2020 polling-calibration reproduction slice."""

import csv
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import calibrate_polling_2006_2020 as calibration  # noqa: E402


class FrozenHistoricalCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = calibration.load_signals()

    def test_sample_membership_and_horizon_counts(self):
        self.assertEqual(len(self.rows), 531)
        primary = [r for r in self.rows if r["primary_calibration"] == "1"]
        runoff = [r for r in self.rows if r["procedural_runoff_robustness"] == "1"]
        self.assertEqual(len(primary), 527)
        self.assertEqual(len(runoff), 4)
        self.assertEqual({r["polling_signal_id"] for r in runoff}, calibration.RUNOFF_IDS)
        self.assertEqual(Counter(int(r["horizon_days"]) for r in primary),
                         calibration.PRIMARY_COUNTS)
        self.assertEqual(Counter(int(r["cycle"]) for r in self.rows), calibration.CYCLE_COUNTS)

    def test_all_frozen_parameters(self):
        result = calibration.calibrate(self.rows)
        calibration.verify_frozen(result)
        self.assertEqual(result[60]["n"], 93)
        self.assertGreater(result[7]["sigma"], 0)

    def test_runoff_exclusion_changes_calibration(self):
        result = calibration.calibrate(self.rows)
        all_60d = [float(r["actual_margin_dem_minus_rep"]) - float(r["poll_margin_dem_minus_rep"])
                   for r in self.rows if int(r["horizon_days"]) == 60]
        self.assertEqual(len(all_60d), 94)
        self.assertGreater(abs(sum(all_60d) / len(all_60d) - result[60]["mu"]), 1e-3)

    def test_invalid_status_or_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tampered.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]))
                writer.writeheader()
                for i, r in enumerate(self.rows):
                    altered = dict(r)
                    if i == 0:
                        altered["primary_calibration"] = "0"
                    writer.writerow(altered)
            with self.assertRaisesRegex(ValueError, "classification"):
                calibration.load_signals(path)

    def test_freeze_assertion_catches_changed_margin(self):
        tampered = [dict(r) for r in self.rows]
        tampered[0]["poll_margin_dem_minus_rep"] = str(
            float(tampered[0]["poll_margin_dem_minus_rep"]) + 0.01
        )
        with self.assertRaises(AssertionError):
            calibration.verify_frozen(calibration.calibrate(tampered))


if __name__ == "__main__":
    unittest.main()
