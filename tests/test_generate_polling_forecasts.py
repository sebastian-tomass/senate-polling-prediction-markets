"""Regression tests for the poll-level 2022/2024 forecast pipeline."""

import copy
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import generate_polling_forecasts as forecasts  # noqa: E402


class PollingForecastGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.report = forecasts.run()
        cls.by_id = {row["polling_signal_id"]: row for row in cls.rows}
        cls.references = {
            year: forecasts.load_common_support(
                year, forecasts.DATA / f"{year}_common_support.csv"
            )
            for year in forecasts.FORECAST_CYCLES
        }

    def test_exact_forecast_universe_and_horizon_counts(self):
        self.assertEqual(len(self.rows), 98)
        self.assertEqual(Counter(row["cycle"] for row in self.rows), {2022: 38, 2024: 60})
        for cycle, expected in forecasts.EXPECTED_HORIZON_COUNTS.items():
            observed = Counter(
                row["horizon_days"] for row in self.rows if row["cycle"] == cycle
            )
            self.assertEqual(observed, expected)

    def test_rebuilt_historical_calibration_is_applied(self):
        audit = self.report["historical_calibration"]
        self.assertEqual(audit["reconstructed_historical_signals"], 531)
        self.assertEqual(audit["primary_observations"], 527)
        self.assertEqual(audit["runoff_robustness_observations"], 4)
        self.assertLess(audit["max_reconstructed_margin_abs_difference"], 1e-12)
        self.assertLess(audit["max_frozen_parameter_abs_difference"], 1e-12)

        row = self.by_id["2024-arizona-60d"]
        expected_z = (row["poll_weighted_margin"] + row["calibration_mu"]) / row["calibration_sigma"]
        expected_p = 0.5 * (1.0 + math.erf(expected_z / math.sqrt(2.0)))
        self.assertEqual(row["z_poll"], expected_z)
        self.assertEqual(row["p_poll_dem"], expected_p)
        self.assertAlmostEqual(row["p_poll_dem"] + row["p_poll_rep"], 1.0, places=15)

    def test_all_frozen_common_support_forecasts_match(self):
        verification = forecasts.verify_common_support(self.rows, self.references)
        self.assertEqual(verification["common_support_rows_checked"], 94)
        self.assertEqual(verification["rows_checked_by_cycle"], {"2022": 34, "2024": 60})
        self.assertLess(verification["max_probability_abs_difference"], 1e-12)
        self.assertLess(verification["max_2024_margin_abs_difference"], 1e-12)

    def test_georgia_runoff_forecasts_remain_outside_primary_fit(self):
        runoff = {
            row["polling_signal_id"] for row in self.rows
            if row["sample_status"] == "POST_GENERAL_RUNOFF_ROBUSTNESS"
        }
        self.assertEqual(runoff, forecasts.RUNOFF_2022_IDS)
        primary_reference_ids = {
            row["polling_signal_id"] for row in self.references[2022]
        }
        self.assertTrue(runoff.isdisjoint(primary_reference_ids))
        self.assertTrue(all(0 < self.by_id[signal_id]["p_poll_dem"] < 1
                            for signal_id in runoff))

    def test_source_anomaly_flags_are_propagated_without_repair(self):
        observed = {
            row["polling_signal_id"] for row in self.rows
            if row["source_data_anomaly_present"]
        }
        self.assertEqual(observed, forecasts.ANOMALOUS_2024_IDS)
        self.assertFalse(self.by_id["2022-iowa-14d"]["source_data_anomaly_present"])

    def test_changed_frozen_probability_fails_closed(self):
        tampered = {year: [dict(row) for row in rows]
                    for year, rows in self.references.items()}
        tampered[2022][0]["p_poll_dem"] = str(
            float(tampered[2022][0]["p_poll_dem"]) + 0.001
        )
        with self.assertRaisesRegex(AssertionError, "probability mismatch"):
            forecasts.verify_common_support(self.rows, tampered)

    def test_changed_membership_or_margin_fails_closed(self):
        missing = {year: [dict(row) for row in rows]
                   for year, rows in self.references.items()}
        missing[2022].pop()
        with self.assertRaisesRegex(AssertionError, "membership changed"):
            forecasts.verify_common_support(self.rows, missing)

        changed_margin = copy.deepcopy(self.references)
        changed_margin[2024][0]["poll_weighted_margin"] = str(
            float(changed_margin[2024][0]["poll_weighted_margin"]) + 0.001
        )
        with self.assertRaisesRegex(AssertionError, "polling-margin mismatch"):
            forecasts.verify_common_support(self.rows, changed_margin)


if __name__ == "__main__":
    unittest.main()
