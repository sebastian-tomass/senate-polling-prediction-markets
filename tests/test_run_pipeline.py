"""End-to-end regression and presentation-output tests."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fit_hybrid_2022 as development  # noqa: E402
import run_pipeline as pipeline  # noqa: E402


class EndToEndPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary.name) / "outputs"
        cls.report = pipeline.run(output_dir=cls.output_dir)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_stages_reproduce_the_frozen_results(self):
        self.assertTrue(self.report["checks"]["all_frozen_regressions_passed"])
        self.assertEqual(
            self.report["pipeline"]["market_mode"],
            "committed_verified_common_support",
        )
        self.assertEqual(
            self.report["upstream"]["polling"]["pipeline_inputs"]["poll_usages"],
            7_346,
        )
        self.assertEqual(
            self.report["upstream"]["polling"]["pipeline_inputs"]
            ["reconstructed_polling_signals"],
            629,
        )
        self.assertEqual(
            self.report["upstream"]["polling"]["historical_calibration"]
            ["primary_observations"],
            527,
        )
        self.assertEqual(self.report["development_2022"]["sample"]["n_primary"], 34)
        self.assertEqual(self.report["evaluation_2024"]["n_observations"], 60)

    def test_fitted_weight_scores_and_bootstrap_are_exact(self):
        fit = self.report["development_2022"]["fit"]
        self.assertAlmostEqual(fit["w_unconstrained"], -0.3370047170535644, places=12)
        self.assertEqual(fit["w_constrained"], 0.0)

        result = self.report["evaluation_2024"]
        self.assertAlmostEqual(
            result["scores"]["polling"]["equal_horizon"]["brier"],
            0.08748401164864145,
            places=12,
        )
        self.assertAlmostEqual(
            result["scores"]["market"]["equal_horizon"]["brier"],
            0.07610306881127452,
            places=12,
        )
        self.assertAlmostEqual(
            result["paired_equal_horizon_delta"]["brier"],
            0.011380942837366929,
            places=12,
        )
        self.assertAlmostEqual(
            result["bootstrap"]["delta_brier"]["ci_2_5"],
            -0.01123307894190075,
            places=12,
        )
        self.assertAlmostEqual(
            result["bootstrap"]["delta_brier"]["ci_97_5"],
            0.0355836706914058,
            places=12,
        )
        self.assertEqual(result["scores"]["hybrid"], result["scores"]["market"])

    def test_presentation_diagnostics_reproduce_overlap(self):
        diagnostics = self.report["presentation_diagnostics_2024"]
        self.assertEqual(diagnostics["favored_party_agreement_count"], 58)
        self.assertEqual(diagnostics["n_observations"], 60)
        self.assertAlmostEqual(
            diagnostics["probability_correlation"], 0.9730706789649773, places=12
        )
        self.assertAlmostEqual(
            diagnostics["logit_correlation"], 0.9039317978980913, places=12
        )
        self.assertEqual(
            diagnostics["favored_party_disagreements"],
            ["2024-ohio-14d", "2024-ohio-7d"],
        )

    def test_generated_forecasts_feed_the_fit(self):
        with (self.output_dir / "tables/rebuilt_polling_forecasts.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            forecasts = list(csv.DictReader(handle))
        references = pipeline.load_reference_rows()
        market_inputs, _ = pipeline.load_market_inputs(references)

        target = next(
            row for row in forecasts
            if row["polling_signal_id"] == "2022-arizona-60d"
        )
        target["p_poll_dem"] = str(float(target["p_poll_dem"]) + 0.01)
        rows = pipeline.assemble_common_support(
            cycle=2022,
            polling_forecasts=forecasts,
            market_inputs=market_inputs,
            references=references,
        )
        changed = development.fit_hybrid(rows)
        with self.assertRaisesRegex(AssertionError, "Frozen development audit mismatch"):
            development.verify_frozen(changed)

    def test_tables_audit_and_final_figures_are_written(self):
        expected = {
            "tables/rebuilt_polling_forecasts.csv",
            "tables/analysis_common_support_2022.csv",
            "tables/analysis_common_support_2024.csv",
            "tables/calibration_parameters.csv",
            "tables/headline_results.csv",
            "tables/scores_by_horizon.csv",
            "tables/bootstrap_intervals.csv",
            "tables/end_to_end_audit.json",
            "figures/2022_hybrid_weight_objective.png",
            "figures/2022_hybrid_weight_objective.svg",
            "figures/2024_scores_by_horizon.png",
            "figures/2024_scores_by_horizon.svg",
            "figures/2024_poll_market_probabilities.png",
            "figures/2024_poll_market_probabilities.svg",
        }
        self.assertEqual(set(self.report["artifacts"]), expected)
        for relative in expected:
            path = self.output_dir / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 100, relative)

        png = self.output_dir / "figures/2024_scores_by_horizon.png"
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        svg = self.output_dir / "figures/2024_scores_by_horizon.svg"
        self.assertIn("<svg", svg.read_text(encoding="utf-8")[:1_000])

        audit = json.loads(
            (self.output_dir / "tables/end_to_end_audit.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(audit["checks"]["all_frozen_regressions_passed"])
        self.assertEqual(audit["artifacts"], self.report["artifacts"])


if __name__ == "__main__":
    unittest.main()
