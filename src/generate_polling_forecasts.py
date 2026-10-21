"""Rebuild 2022 and 2024 Senate polling forecasts from poll-level inputs.

Run from the repository root:
    python src/generate_polling_forecasts.py
    python src/generate_polling_forecasts.py --csv outputs/tables/rebuilt_polling_forecasts.csv

The pipeline reconstructs all poll weights and race-by-horizon margins, replaces
the stored historical margins with those reconstructed values when estimating
the 2006-2020 calibration, and then converts the 2022/2024 margins to Democratic
win probabilities. Frozen signal and common-support values are validation
targets only; no market probability or election outcome enters a forecast.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import calibrate_polling_2006_2020 as calibration
import reconstruct_poll_weights as poll_weights

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
HORIZONS = (60, 30, 14, 7)
FORECAST_CYCLES = (2022, 2024)
EXPECTED_SIGNAL_COUNTS = {2022: 38, 2024: 60}
EXPECTED_HORIZON_COUNTS = {
    2022: {60: 8, 30: 9, 14: 10, 7: 11},
    2024: {60: 12, 30: 17, 14: 15, 7: 16},
}
COMMON_SUPPORT_COUNTS = {2022: 34, 2024: 60}
RUNOFF_2022_IDS = {f"2022-georgia-{h}d" for h in HORIZONS}
ANOMALOUS_2024_IDS = {"2024-arizona-14d", "2024-arizona-7d"}
PROBABILITY_TOLERANCE = 1e-12
MARGIN_TOLERANCE = 1e-12


def _standard_normal_cdf(z: float) -> float:
    """Standard normal CDF using the error function available in Python."""
    if not math.isfinite(z):
        raise ValueError("The polling z score must be finite")
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _signal_metadata(row_weights: list[dict]) -> dict[str, dict]:
    """Recover one validated metadata record per reconstructed polling signal."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in row_weights:
        grouped[row["polling_signal_id"]].append(row)

    metadata: dict[str, dict] = {}
    for signal_id, rows in grouped.items():
        dimensions = {
            "cycle": {int(row["cycle"]) for row in rows},
            "state": {row["state"] for row in rows},
            "horizon_days": {int(row["horizon_days"]) for row in rows},
            "cutoff_date": {row["cutoff_date"] for row in rows},
        }
        inconsistent = {key: values for key, values in dimensions.items() if len(values) != 1}
        if inconsistent:
            raise ValueError(f"Inconsistent poll-level metadata for {signal_id}: {inconsistent}")
        metadata[signal_id] = {
            key: next(iter(values)) for key, values in dimensions.items()
        }
        metadata[signal_id]["source_data_anomaly_present"] = any(
            row["source_data_anomaly"] == "True" for row in rows
        )
    return metadata


def rebuild_historical_calibration(
    reconstructed_signals: list[dict],
    historical_rows: list[dict],
) -> tuple[dict[int, dict], dict]:
    """Estimate calibration after substituting reconstructed historical margins."""
    rebuilt = {
        row["polling_signal_id"]: row
        for row in reconstructed_signals
        if int(row["cycle"]) <= 2020
    }
    frozen = {row["polling_signal_id"]: row for row in historical_rows}
    if len(rebuilt) != 531 or set(rebuilt) != set(frozen):
        missing = sorted(set(frozen) - set(rebuilt))
        extra = sorted(set(rebuilt) - set(frozen))
        raise ValueError(
            f"Historical reconstructed-signal join changed: missing={missing[:5]}, extra={extra[:5]}"
        )

    substituted = []
    max_margin_difference = 0.0
    for source in historical_rows:
        signal_id = source["polling_signal_id"]
        signal = rebuilt[signal_id]
        if (int(source["cycle"]) != int(signal["cycle"])
                or int(source["horizon_days"]) != int(signal["horizon_days"])):
            raise ValueError(f"Historical signal metadata mismatch: {signal_id}")
        margin = float(signal["v2_p2_weighted_poll_margin"])
        max_margin_difference = max(
            max_margin_difference,
            abs(margin - float(source["poll_margin_dem_minus_rep"])),
        )
        row = dict(source)
        row["poll_margin_dem_minus_rep"] = str(margin)
        substituted.append(row)

    parameters = calibration.calibrate(substituted)
    calibration.verify_frozen(parameters)
    max_parameter_difference = max(
        abs(float(parameters[horizon][field])
            - float(calibration.FROZEN_PARAMETERS[horizon][field]))
        for horizon in HORIZONS
        for field in ("mu", "sigma", "mae")
    )
    return parameters, {
        "reconstructed_historical_signals": len(rebuilt),
        "primary_observations": sum(
            row["primary_calibration"] == "1" for row in substituted
        ),
        "runoff_robustness_observations": sum(
            row["procedural_runoff_robustness"] == "1" for row in substituted
        ),
        "max_reconstructed_margin_abs_difference": max_margin_difference,
        "max_frozen_parameter_abs_difference": max_parameter_difference,
    }


def generate_forecasts(
    reconstructed_signals: list[dict],
    row_weights: list[dict],
    parameters: dict[int, dict],
) -> list[dict]:
    """Transform independently rebuilt polling margins into win probabilities."""
    metadata = _signal_metadata(row_weights)
    forecasts = []
    for signal in reconstructed_signals:
        cycle = int(signal["cycle"])
        if cycle not in FORECAST_CYCLES:
            continue
        signal_id = signal["polling_signal_id"]
        if signal_id not in metadata:
            raise ValueError(f"Missing poll-level metadata for {signal_id}")
        meta = metadata[signal_id]
        horizon = int(signal["horizon_days"])
        if horizon not in HORIZONS or meta["cycle"] != cycle or meta["horizon_days"] != horizon:
            raise ValueError(f"Invalid forecast cycle or horizon metadata for {signal_id}")
        parameter = parameters[horizon]
        margin = float(signal["v2_p2_weighted_poll_margin"])
        z_score = (margin + parameter["mu"]) / parameter["sigma"]
        probability_dem = _standard_normal_cdf(z_score)
        if not 0.0 < probability_dem < 1.0:
            raise ValueError(f"Non-interior polling probability for {signal_id}")

        if cycle == 2022:
            sample_status = (
                "POST_GENERAL_RUNOFF_ROBUSTNESS"
                if signal_id in RUNOFF_2022_IDS else "PRIMARY_2022"
            )
        else:
            sample_status = "PRIMARY_2024"

        forecasts.append({
            "polling_signal_id": signal_id,
            "cycle": cycle,
            "state": meta["state"],
            "horizon_days": horizon,
            "cutoff_date": meta["cutoff_date"],
            "sample_status": sample_status,
            "poll_count": int(signal["poll_count"]),
            "distinct_pollsters": int(signal["distinct_v1_canonical_pollsters"]),
            "v2_p2_total_weight": float(signal["v2_p2_total_weight"]),
            "poll_weighted_margin": margin,
            "calibration_n_primary": int(parameter["n"]),
            "calibration_mu": float(parameter["mu"]),
            "calibration_sigma": float(parameter["sigma"]),
            "z_poll": z_score,
            "p_poll_dem": probability_dem,
            "p_poll_rep": 1.0 - probability_dem,
            "source_data_anomaly_present": bool(meta["source_data_anomaly_present"]),
        })

    counts = Counter(row["cycle"] for row in forecasts)
    if dict(counts) != EXPECTED_SIGNAL_COUNTS:
        raise AssertionError(f"Unexpected forecast counts: {dict(counts)}")
    for cycle, expected in EXPECTED_HORIZON_COUNTS.items():
        observed = Counter(
            row["horizon_days"] for row in forecasts if row["cycle"] == cycle
        )
        if dict(observed) != expected:
            raise AssertionError(f"Unexpected {cycle} horizon counts: {dict(observed)}")

    runoff = {row["polling_signal_id"] for row in forecasts
              if row["sample_status"] == "POST_GENERAL_RUNOFF_ROBUSTNESS"}
    if runoff != RUNOFF_2022_IDS:
        raise AssertionError(f"Unexpected 2022 runoff-robustness forecasts: {runoff}")
    anomalies = {row["polling_signal_id"] for row in forecasts
                 if row["source_data_anomaly_present"]}
    if anomalies != ANOMALOUS_2024_IDS:
        raise AssertionError(f"Unexpected forecast anomaly flags: {anomalies}")
    return forecasts


def load_common_support(year: int, path: Path) -> list[dict[str, str]]:
    """Load only the frozen fields needed to validate generated forecasts."""
    if year not in FORECAST_CYCLES:
        raise ValueError(f"Unsupported common-support cycle: {year}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "polling_signal_id", "state", "horizon_days", "cutoff_date", "p_poll_dem"
        }
        if year == 2022:
            required.add("sample_status")
        else:
            required.update({"poll_weighted_margin", "source_data_anomaly_present"})
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{year} common-support CSV missing columns: {sorted(missing)}")
        rows = list(reader)
    ids = [row["polling_signal_id"] for row in rows]
    if len(rows) != COMMON_SUPPORT_COUNTS[year] or len(ids) != len(set(ids)):
        raise ValueError(
            f"Expected {COMMON_SUPPORT_COUNTS[year]} unique {year} common-support rows"
        )
    return rows


def verify_common_support(
    forecasts: list[dict],
    references: dict[int, list[dict[str, str]]],
    *,
    probability_tolerance: float = PROBABILITY_TOLERANCE,
    margin_tolerance: float = MARGIN_TOLERANCE,
) -> dict:
    """Regression-check generated forecasts against the committed frozen samples."""
    generated = {row["polling_signal_id"]: row for row in forecasts}
    expected_ids = {
        2022: {row["polling_signal_id"] for row in forecasts
               if row["cycle"] == 2022 and row["sample_status"] == "PRIMARY_2022"},
        2024: {row["polling_signal_id"] for row in forecasts if row["cycle"] == 2024},
    }
    max_probability_difference = 0.0
    max_2024_margin_difference = 0.0
    checked = 0

    for year in FORECAST_CYCLES:
        rows = references[year]
        reference_ids = {row["polling_signal_id"] for row in rows}
        if reference_ids != expected_ids[year]:
            missing = sorted(expected_ids[year] - reference_ids)
            extra = sorted(reference_ids - expected_ids[year])
            raise AssertionError(
                f"{year} common-support membership changed: missing={missing}, extra={extra}"
            )
        for reference in rows:
            signal_id = reference["polling_signal_id"]
            forecast = generated[signal_id]
            if (reference["state"] != forecast["state"]
                    or int(reference["horizon_days"]) != forecast["horizon_days"]
                    or reference["cutoff_date"] != forecast["cutoff_date"]):
                raise AssertionError(f"Frozen common-support metadata mismatch: {signal_id}")
            probability_difference = abs(
                float(reference["p_poll_dem"]) - forecast["p_poll_dem"]
            )
            max_probability_difference = max(
                max_probability_difference, probability_difference
            )
            if probability_difference > probability_tolerance:
                raise AssertionError(
                    f"Frozen polling-probability mismatch for {signal_id}: "
                    f"{probability_difference}"
                )

            if year == 2022 and reference["sample_status"] != "PRIMARY_2022":
                raise AssertionError(f"Non-PRIMARY row entered the 2022 fit: {signal_id}")
            if year == 2024:
                margin_difference = abs(
                    float(reference["poll_weighted_margin"])
                    - forecast["poll_weighted_margin"]
                )
                max_2024_margin_difference = max(
                    max_2024_margin_difference, margin_difference
                )
                if margin_difference > margin_tolerance:
                    raise AssertionError(
                        f"Frozen 2024 polling-margin mismatch for {signal_id}: "
                        f"{margin_difference}"
                    )
                expected_anomaly = reference["source_data_anomaly_present"] == "true"
                if expected_anomaly != forecast["source_data_anomaly_present"]:
                    raise AssertionError(f"Frozen anomaly flag mismatch: {signal_id}")
            checked += 1

    return {
        "common_support_rows_checked": checked,
        "rows_checked_by_cycle": {
            str(year): len(references[year]) for year in FORECAST_CYCLES
        },
        "max_probability_abs_difference": max_probability_difference,
        "max_2024_margin_abs_difference": max_2024_margin_difference,
    }


def run(data_dir: Path = DATA) -> tuple[list[dict], dict]:
    """Run poll weighting, historical calibration, forecast generation and checks."""
    row_weights, reconstructed_signals, weighting_summary = poll_weights.run(data_dir)
    historical_rows = calibration.load_signals(
        data_dir / "2006_2020_polling_signals.csv"
    )
    parameters, calibration_summary = rebuild_historical_calibration(
        reconstructed_signals, historical_rows
    )
    forecasts = generate_forecasts(reconstructed_signals, row_weights, parameters)
    references = {
        year: load_common_support(year, data_dir / f"{year}_common_support.csv")
        for year in FORECAST_CYCLES
    }
    verification = verify_common_support(forecasts, references)
    verification["max_upstream_signal_abs_difference"] = weighting_summary[
        "max_signal_abs_difference"
    ]
    verification["frozen_audit_verified"] = True

    report = {
        "pipeline_inputs": {
            "poll_usages": len(row_weights),
            "reconstructed_polling_signals": len(reconstructed_signals),
        },
        "historical_calibration": {
            **calibration_summary,
            "parameters": {str(h): parameters[h] for h in HORIZONS},
        },
        "polling_forecasts": {
            "total": len(forecasts),
            "by_cycle": {
                str(year): sum(row["cycle"] == year for row in forecasts)
                for year in FORECAST_CYCLES
            },
            "by_cycle_and_horizon": {
                str(year): {
                    str(h): sum(
                        row["cycle"] == year and row["horizon_days"] == h
                        for row in forecasts
                    )
                    for h in HORIZONS
                }
                for year in FORECAST_CYCLES
            },
            "primary_2022": sum(
                row["sample_status"] == "PRIMARY_2022" for row in forecasts
            ),
            "runoff_robustness_2022": sum(
                row["sample_status"] == "POST_GENERAL_RUNOFF_ROBUSTNESS"
                for row in forecasts
            ),
            "primary_2024": sum(
                row["sample_status"] == "PRIMARY_2024" for row in forecasts
            ),
        },
        "verification": verification,
    }
    return forecasts, report


def export_csv(path: Path, forecasts: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(forecasts[0]))
        writer.writeheader()
        writer.writerows(forecasts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="Optional 98-row forecast output")
    parser.add_argument("--json", type=Path, help="Optional machine-readable audit summary")
    args = parser.parse_args()

    forecasts, report = run()
    if args.csv:
        export_csv(args.csv, forecasts)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(payload, end="")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
