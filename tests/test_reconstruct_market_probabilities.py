"""Tests for checksum-pinned prediction-market reconstruction."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import reconstruct_market_probabilities as markets  # noqa: E402


class MarketProbabilityReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = markets.load_manifest()
        cls.references = {
            year: markets.load_common_support(
                year, markets.DATA / f"{year}_common_support.csv"
            )
            for year in (2022, 2024)
        }

    def test_manifest_matches_committed_common_support_lineage(self):
        markets.validate_manifest_lineage(self.manifest, self.references[2022])
        source_2022 = self.manifest["sources"]["2022"]
        source_2024 = self.manifest["sources"]["2024"]
        self.assertEqual(len(source_2022["files"]), 10)
        self.assertEqual(len(source_2024["files"]), 1)
        self.assertEqual(
            source_2024["files"][0]["git_blob_sha"],
            "23c902a99fc4b92882226f7bd5b28aeaac37840e",
        )
        for source in (source_2022, source_2024):
            self.assertIsNone(source["license_file_at_pinned_commit"])
            self.assertEqual(
                source["redistribution_policy"], "upstream_only_not_vendored"
            )

    def test_git_blob_sha_uses_git_object_encoding(self):
        self.assertEqual(
            markets.git_blob_sha(b"hello\n"),
            "ce013625030ba8dba906f756967f9e9ca394464a",
        )

    def test_2022_selection_uses_cutoff_and_first_source_row_tie_break(self):
        payload = (
            ",Timestamp,Account,Type,Outcome,Direction,Amount,Shares,Price,Var.9,Var.10\n"
            "1,2022-10-01 12:00:01,a,Buy,Democrat,x,1,2,0.90,,Tx\n"
            "2,2022-10-01 11:59:00,b,Buy,Republican,x,3,4,0.40,,Tx\n"
            "3,2022-10-01 11:59:00,c,Buy,Democrat,x,5,6,0.70,,Tx\n"
            "4,2022-10-01 10:00:00,d,Buy,Democrat,x,7,8,0.30,,Tx\n"
        ).encode()
        trades = markets.parse_2022_trades(payload, "synthetic.csv")
        target = datetime(2022, 10, 1, 12, tzinfo=timezone.utc)
        selected = markets.select_2022_trade(trades, target)
        self.assertEqual(selected["source_row"], 3)
        self.assertEqual(selected["outcome"], "Republican")
        self.assertEqual(1.0 - selected["price"], 0.6)

    def test_2022_democratic_contract_keeps_price(self):
        payload = (
            ",Timestamp,Account,Type,Outcome,Direction,Amount,Shares,Price,Var.9,Var.10\n"
            "1,2022-10-01 11:00:00,a,Buy,Democrat,x,1,2,0.73,,Tx\n"
        ).encode()
        selected = markets.select_2022_trade(
            markets.parse_2022_trades(payload, "synthetic.csv"),
            datetime(2022, 10, 1, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["outcome"], "Democrat")
        self.assertEqual(selected["price"], 0.73)

    def test_2024_selection_uses_nearest_scheduled_grid_point(self):
        target = datetime(2024, 10, 6, 12, tzinfo=timezone.utc)
        epoch = int(target.timestamp())
        samples = [
            {"t": epoch - 43_200, "p": 0.50},
            {"t": epoch + 2, "p": 0.65},
            {"t": epoch + 43_200, "p": 0.70},
        ]
        index, selected = markets.select_2024_observation(samples, target)
        self.assertEqual(index, 1)
        self.assertEqual(selected, {"t": epoch + 2, "p": 0.65})

    def test_2024_missing_scheduled_point_fails_closed(self):
        target = datetime(2024, 10, 6, 12, tzinfo=timezone.utc)
        epoch = int(target.timestamp())
        with self.assertRaisesRegex(ValueError, "No 2024 CLOB grid point"):
            markets.select_2024_observation(
                [{"t": epoch - 43_200, "p": 0.5}], target
            )

    def test_source_hash_mismatch_fails_before_parsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_file = root / "source.csv"
            source_file.write_bytes(b"tampered")
            source = {
                "repository": "owner/repository",
                "commit": "a" * 40,
            }
            entry = {"path": "source.csv", "git_blob_sha": "b" * 40}
            with self.assertRaisesRegex(ValueError, "Git blob SHA mismatch"):
                markets.acquire_source(
                    cycle=2022,
                    source=source,
                    file_entry=entry,
                    cache_dir=root / "cache",
                    offline=True,
                    local_path=source_file,
                )

    def test_frozen_verifier_rejects_probability_change(self):
        rebuilt = []
        for year, rows in self.references.items():
            for reference in rows:
                rebuilt.append({
                    "polling_signal_id": reference["polling_signal_id"],
                    "cycle": year,
                    "state": reference["state"],
                    "horizon_days": int(reference["horizon_days"]),
                    "cutoff_date": reference["cutoff_date"],
                    "p_market_dem": float(reference["p_market_dem"]),
                    "source_file": reference.get("market_source_file", "archive.json"),
                    "source_git_blob_sha": reference.get(
                        "market_source_blob_sha", "c" * 40
                    ),
                    "market_source_timestamp_utc": reference.get(
                        "market_observed_timestamp_utc", "2022-01-01T00:00:00Z"
                    ),
                })
        # The 2024 lineage fields are not frozen in the compact reference; only its
        # timestamp and probability enter this regression check.
        markets.verify_frozen(rebuilt, self.references)
        changed = copy.deepcopy(rebuilt)
        changed[0]["p_market_dem"] += 0.001
        with self.assertRaisesRegex(AssertionError, "market-probability mismatch"):
            markets.verify_frozen(changed, self.references)

    def test_manifest_rejects_unsafe_source_path(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["sources"]["2022"]["files"][0]["path"] = "../escape.csv"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsafe source path"):
                markets.load_manifest(path)


if __name__ == "__main__":
    unittest.main()
