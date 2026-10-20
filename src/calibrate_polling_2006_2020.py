"""Reproduce frozen 2006–2020 Senate polling-error calibration from signal-level data.

Run from the repository root:
    python src/calibrate_polling_2006_2020.py

The 531 already-aggregated, final-model historical polling signals are INPUTS.
Their upstream poll-level construction is a separate pipeline stage.
No pollster-quality weights or poll-level weights are reconstructed here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import fmean, stdev

HORIZONS = (60, 30, 14, 7)
CYCLES = (2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020)
PRIMARY_COUNTS = {60: 93, 30: 133, 14: 150, 7: 151}
CYCLE_COUNTS = {2006: 33, 2008: 69, 2010: 70, 2012: 79, 2014: 98,
                2016: 69, 2018: 70, 2020: 43}
RUNOFF_IDS = {f"2008-georgia-{h}d" for h in HORIZONS}
INPUT_PATH = Path(__file__).resolve().parents[1] / "data/processed/2006_2020_polling_signals.csv"

# Frozen historical audit regression targets (not inputs to parameter estimation).
# Internal source: 'V2 P2 Polling Error Parameters'!A8:E11.
FROZEN_PARAMETERS = {
    60: {"n": 93, "mu": -1.3274772919479318, "sigma": 7.476124549545835,
         "mae": 6.236135121586347},
    30: {"n": 133, "mu": -0.6541356488003056, "sigma": 6.082071238285374,
         "mae": 4.97037651104371},
    14: {"n": 150, "mu": -0.48976516300760903, "sigma": 6.206312401891217,
         "mae": 4.8096276884374385},
    7: {"n": 151, "mu": -0.633235670174805, "sigma": 6.09209692815215,
        "mae": 4.536644087503184},
}

REQUIRED = {
    "polling_signal_id", "cycle", "state", "horizon_days", "cutoff_date",
    "poll_count", "poll_margin_dem_minus_rep", "v2_p2_total_weight",
    "actual_margin_dem_minus_rep", "sample_status", "primary_calibration",
    "procedural_runoff_robustness", "outcome_source", "outcome_source_url",
    "outcome_merge_status", "signal_source_sheet", "signal_source_excel_row",
    "frozen_error_for_validation",
}


def load_signals(path: Path = INPUT_PATH) -> list[dict]:
    """Validate the original 531-record, frozen historical signal universe."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(set(reader.fieldnames or ())):
            raise ValueError(f"Missing required columns: {sorted(REQUIRED - set(reader.fieldnames or ())) }")
        rows = list(reader)
    if len(rows) != 531:
        raise ValueError(f"Expected 531 frozen historical signals, got {len(rows)}")
    ids = [r["polling_signal_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate polling_signal_id values")

    annual = Counter()
    primary_by_horizon = Counter()
    runoff_ids = set()
    for r in rows:
        key = r["polling_signal_id"]
        try:
            cycle = int(r["cycle"])
            horizon = int(r["horizon_days"])
            cutoff = date.fromisoformat(r["cutoff_date"])
            poll_count = int(r["poll_count"])
            poll_margin = float(r["poll_margin_dem_minus_rep"])
            actual_margin = float(r["actual_margin_dem_minus_rep"])
            weight = float(r["v2_p2_total_weight"])
            archived_error = float(r["frozen_error_for_validation"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Malformed signal fields for {key}") from exc
        if cycle not in CYCLES or horizon not in HORIZONS or cutoff.year != cycle:
            raise ValueError(f"Unexpected cycle/horizon/cutoff for {key}")
        if key != f"{cycle}-{r['state'].strip().lower().replace(' ', '_')}-{horizon}d":
            raise ValueError(f"Signal ID inconsistent with cycle/state/horizon: {key}")
        if poll_count <= 0 or not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"Invalid poll count or total weight for {key}")
        if not all(map(math.isfinite, (poll_margin, actual_margin, archived_error))):
            raise ValueError(f"Nonfinite margin/error for {key}")
        if not math.isclose(actual_margin - poll_margin, archived_error, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f"Stored historical error differs from actual minus polling margin for {key}")
        if (not r["outcome_source"] or not r["outcome_source_url"]
                or r["outcome_merge_status"] != "VERIFIED_FEC"):
            raise ValueError(f"Missing certified-result provenance for {key}")

        primary, runoff = r["primary_calibration"], r["procedural_runoff_robustness"]
        if primary == "1" and runoff == "0" and r["sample_status"] == "PRIMARY_V1_1":
            primary_by_horizon[horizon] += 1
        elif primary == "0" and runoff == "1" and r["sample_status"] == "POST_GE_RUNOFF_ROBUSTNESS":
            runoff_ids.add(key)
        else:
            raise ValueError(f"Inconsistent PRIMARY/runoff classification for {key}")
        annual[cycle] += 1

    if dict(annual) != CYCLE_COUNTS:
        raise ValueError(f"Historical signal universe changed: {dict(annual)}")
    if dict(primary_by_horizon) != PRIMARY_COUNTS:
        raise ValueError(f"PRIMARY horizon counts changed: {dict(primary_by_horizon)}")
    if runoff_ids != RUNOFF_IDS:
        raise ValueError(f"Expected exactly four Georgia 2008 runoff signals: {runoff_ids}")
    return rows


def calibrate(rows: list[dict]) -> dict[int, dict]:
    """Unweighted PRIMARY mean error and Bessel-corrected sample SD for each horizon.

    Historical error = certified Democratic-minus-Republican margin minus the
    pre-election quality-weighted Democratic-minus-Republican polling margin.
    """
    if len(rows) != 531:
        raise ValueError("Calibration requires the full frozen 531-signal input")
    primary = [r for r in rows if r["primary_calibration"] == "1"]
    if len(primary) != 527:
        raise ValueError("Calibration requires exactly 527 PRIMARY observations")
    results: dict[int, dict] = {}
    for horizon in HORIZONS:
        errors = [float(r["actual_margin_dem_minus_rep"])
                  - float(r["poll_margin_dem_minus_rep"])
                  for r in primary if int(r["horizon_days"]) == horizon]
        if len(errors) != PRIMARY_COUNTS[horizon]:
            raise ValueError(f"Wrong PRIMARY N for {horizon}d")
        results[horizon] = {
            "n": len(errors),
            "mu": fmean(errors),
            "sigma": stdev(errors),  # ddof=1 (the workbook's N-1 specification)
            "mae": fmean(abs(e) for e in errors),
        }
        if not results[horizon]["sigma"] > 0:
            raise ValueError(f"Nonpositive sigma at {horizon}d")
    return results


def verify_frozen(results: dict[int, dict], *, tolerance: float = 1e-12) -> None:
    """Regression-test calculated values against immutable audit-workbook benchmarks."""
    if set(results) != set(FROZEN_PARAMETERS):
        raise AssertionError("Missing calibration horizons")
    for horizon in HORIZONS:
        for field, reference in FROZEN_PARAMETERS[horizon].items():
            observed = results[horizon][field]
            if field == "n":
                matches = observed == reference
            else:
                matches = math.isclose(observed, reference, rel_tol=0, abs_tol=tolerance)
            if not matches:
                raise AssertionError(
                    f"Frozen {horizon}d {field} mismatch: observed {observed}, expected {reference}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=INPUT_PATH,
                        help="Frozen processed historical signal-level CSV")
    parser.add_argument("--json", type=Path, help="Optional output path for machine-readable calibration")
    parser.add_argument("--csv", type=Path, help="Optional output path for the four-row parameter table")
    args = parser.parse_args()

    rows = load_signals(args.data)
    results = calibrate(rows)
    verify_frozen(results)
    print("Frozen historical signal universe: 531 (527 PRIMARY; 4 Georgia 2008 runoff robustness)")
    print("Horizon       N                mu_p2             sigma_p2             MAE_p2")
    for horizon in HORIZONS:
        r = results[horizon]
        print(f"{horizon:>3}d       {r['n']:>3}    {r['mu']:>20.15f}  {r['sigma']:>20.15f}  {r['mae']:>20.15f}")
    print("Frozen calibration regression: PASS (absolute tolerance 1e-12)")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "source_signals": len(rows), "primary_observations": 527,
            "runoff_robustness_observations": 4,
            "historical_cycles": list(CYCLES),
            "parameters": {str(h): results[h] for h in HORIZONS},
            "frozen_regression_verified": True,
        }, indent=2) + "\n", encoding="utf-8")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["horizon_days", "n_primary", "mu_p2", "sigma_p2", "mae_p2"])
            for h in HORIZONS:
                r = results[h]
                writer.writerow([h, r["n"], r["mu"], r["sigma"], r["mae"]])


if __name__ == "__main__":
    main()
