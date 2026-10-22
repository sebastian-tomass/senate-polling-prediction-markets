"""Run the complete frozen Senate polling/market reproduction pipeline.

Run from the repository root:

    python src/run_pipeline.py

The default command is deterministic and offline: it reconstructs poll-level
weights, historical calibration, and 2022/2024 polling forecasts, then joins
the committed, already-verified market probabilities and certified outcomes
for the 2022 fit and locked-spec 2024 evaluation. Add ``--rebuild-markets`` to
repeat the checksum-pinned raw market reconstruction before those joins.

Generated tables and presentation figures are written below ``outputs/`` and
remain outside version control.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import build_presentation as presentation
import evaluate_2024 as evaluation  # noqa: E402
import fit_hybrid_2022 as development  # noqa: E402
import generate_polling_forecasts as polling  # noqa: E402
import reconstruct_market_probabilities as markets  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
HORIZONS = (60, 30, 14, 7)


def load_reference_rows(data_dir: Path = DATA) -> dict[int, list[dict[str, str]]]:
    """Load the fixed common-support membership, outcomes, and audit targets."""
    references = {
        year: polling.load_common_support(
            year, data_dir / f"{year}_common_support.csv"
        )
        for year in polling.FORECAST_CYCLES
    }
    for year, rows in references.items():
        for row in rows:
            missing = {
                "y_dem_win",
                "p_market_dem",
            } - set(row)
            if missing:
                raise ValueError(
                    f"{year} common-support CSV missing end-to-end fields: "
                    f"{sorted(missing)}"
                )
            if row["y_dem_win"] not in {"0", "1"}:
                raise ValueError(
                    f"Invalid certified outcome for {row['polling_signal_id']}"
                )
    return references


def _unique_by_id(rows: list[dict], label: str) -> dict[str, dict]:
    by_id = {row["polling_signal_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError(f"Duplicate polling_signal_id in {label}")
    return by_id


def load_market_inputs(
    references: dict[int, list[dict[str, str]]],
    *,
    rebuild: bool = False,
    data_dir: Path = DATA,
    manifest_path: Path = markets.DEFAULT_MANIFEST,
    cache_dir: Path = markets.DEFAULT_CACHE,
    offline: bool = False,
    source_2022_root: Path | None = None,
    source_2024_json: Path | None = None,
) -> tuple[list[dict], dict]:
    """Return market inputs from committed checks or the pinned raw sources."""
    if rebuild:
        rebuilt, report = markets.run(
            data_dir=data_dir,
            manifest_path=manifest_path,
            cache_dir=cache_dir,
            offline=offline,
            source_2022_root=source_2022_root,
            source_2024_json=source_2024_json,
        )
        return rebuilt, {
            "mode": "reconstructed_pinned_sources",
            **report,
        }

    rows = []
    for year in polling.FORECAST_CYCLES:
        for reference in references[year]:
            rows.append({
                "polling_signal_id": reference["polling_signal_id"],
                "cycle": year,
                "state": reference["state"],
                "horizon_days": int(reference["horizon_days"]),
                "cutoff_date": reference["cutoff_date"],
                "p_market_dem": float(reference["p_market_dem"]),
                "source_mode": "committed_common_support",
            })
    return rows, {
        "mode": "committed_verified_common_support",
        "market_probabilities": {
            "total": len(rows),
            "by_cycle": {
                str(year): sum(row["cycle"] == year for row in rows)
                for year in polling.FORECAST_CYCLES
            },
        },
        "note": (
            "Offline default. Run with --rebuild-markets to reacquire, "
            "checksum, normalize, and reverify the pinned raw archives."
        ),
    }


def assemble_common_support(
    *,
    cycle: int,
    polling_forecasts: list[dict],
    market_inputs: list[dict],
    references: dict[int, list[dict[str, str]]],
    hybrid_weight: float | None = None,
) -> list[dict]:
    """Join regenerated signals to fixed membership and certified outcomes."""
    if cycle not in polling.FORECAST_CYCLES:
        raise ValueError(f"Unsupported analysis cycle: {cycle}")
    if cycle == 2024 and hybrid_weight is None:
        raise ValueError("The locked 2024 hybrid requires the fitted 2022 weight")

    forecast_by_id = _unique_by_id(polling_forecasts, "polling forecasts")
    market_by_id = _unique_by_id(market_inputs, "market inputs")
    reference_rows = references[cycle]
    expected_ids = {row["polling_signal_id"] for row in reference_rows}
    available_market_ids = {
        signal_id
        for signal_id, row in market_by_id.items()
        if int(row["cycle"]) == cycle
    }
    if available_market_ids != expected_ids:
        missing = sorted(expected_ids - available_market_ids)
        extra = sorted(available_market_ids - expected_ids)
        raise ValueError(
            f"{cycle} market join membership changed: missing={missing}, extra={extra}"
        )

    joined = []
    for reference in reference_rows:
        signal_id = reference["polling_signal_id"]
        if signal_id not in forecast_by_id:
            raise ValueError(f"Missing regenerated polling forecast: {signal_id}")
        forecast = forecast_by_id[signal_id]
        market = market_by_id[signal_id]
        horizon = int(reference["horizon_days"])
        metadata = (reference["state"], horizon, reference["cutoff_date"])
        if metadata != (
            forecast["state"],
            int(forecast["horizon_days"]),
            forecast["cutoff_date"],
        ):
            raise ValueError(f"Polling metadata mismatch in end-to-end join: {signal_id}")
        if metadata != (
            market["state"],
            int(market["horizon_days"]),
            market["cutoff_date"],
        ):
            raise ValueError(f"Market metadata mismatch in end-to-end join: {signal_id}")

        p_poll = float(forecast["p_poll_dem"])
        p_market = float(market["p_market_dem"])
        if not all(math.isfinite(value) and 0.0 < value < 1.0
                   for value in (p_poll, p_market)):
            raise ValueError(f"Non-interior end-to-end probability: {signal_id}")

        base = {
            "polling_signal_id": signal_id,
            "state": reference["state"],
            "horizon_days": horizon,
            "cutoff_date": reference["cutoff_date"],
            "p_poll_dem": p_poll,
            "p_market_dem": p_market,
            "y_dem_win": reference["y_dem_win"],
        }
        if cycle == 2022:
            if forecast["sample_status"] != "PRIMARY_2022":
                raise ValueError(f"Non-PRIMARY row entered development: {signal_id}")
            base["sample_status"] = forecast["sample_status"]
        else:
            weight = float(hybrid_weight)
            base.update({
                "p_hybrid_dem": weight * p_poll + (1.0 - weight) * p_market,
                "poll_weighted_margin": float(forecast["poll_weighted_margin"]),
                "source_data_anomaly_present": (
                    "true" if forecast["source_data_anomaly_present"] else "false"
                ),
            })
        joined.append(base)

    expected_count = polling.COMMON_SUPPORT_COUNTS[cycle]
    if len(joined) != expected_count:
        raise AssertionError(
            f"Expected {expected_count} joined {cycle} observations, got {len(joined)}"
        )
    return joined


def presentation_diagnostics(rows: list[dict]) -> dict:
    """Compute compact 2024 overlap diagnostics used in the final presentation."""
    poll = np.array([float(row["p_poll_dem"]) for row in rows], dtype=float)
    market = np.array([float(row["p_market_dem"]) for row in rows], dtype=float)
    agreement = (poll >= 0.5) == (market >= 0.5)
    logit_poll = np.log(poll / (1.0 - poll))
    logit_market = np.log(market / (1.0 - market))
    disagreements = [
        row["polling_signal_id"]
        for row, same_favorite in zip(rows, agreement)
        if not same_favorite
    ]
    return {
        "favored_party_agreement_count": int(agreement.sum()),
        "n_observations": len(rows),
        "favored_party_agreement_fraction": float(agreement.mean()),
        "probability_correlation": float(np.corrcoef(poll, market)[0, 1]),
        "logit_correlation": float(np.corrcoef(logit_poll, logit_market)[0, 1]),
        "favored_party_disagreements": disagreements,
    }


def run(
    *,
    data_dir: Path = DATA,
    output_dir: Path | None = DEFAULT_OUTPUT_DIR,
    rebuild_markets: bool = False,
    market_manifest: Path = markets.DEFAULT_MANIFEST,
    market_cache_dir: Path = markets.DEFAULT_CACHE,
    market_offline: bool = False,
    source_2022_root: Path | None = None,
    source_2024_json: Path | None = None,
) -> dict:
    """Execute every frozen analytical stage and optionally write deliverables."""
    polling_forecasts, polling_report = polling.run(data_dir)
    references = load_reference_rows(data_dir)
    market_inputs, market_report = load_market_inputs(
        references,
        rebuild=rebuild_markets,
        data_dir=data_dir,
        manifest_path=market_manifest,
        cache_dir=market_cache_dir,
        offline=market_offline,
        source_2022_root=source_2022_root,
        source_2024_json=source_2024_json,
    )

    development_rows = assemble_common_support(
        cycle=2022,
        polling_forecasts=polling_forecasts,
        market_inputs=market_inputs,
        references=references,
    )
    development_report = development.fit_hybrid(development_rows)
    development.verify_frozen(development_report)
    development_report["frozen_audit_verified"] = True

    fitted_weight = development_report["fit"]["w_constrained"]
    evaluation_rows = assemble_common_support(
        cycle=2024,
        polling_forecasts=polling_forecasts,
        market_inputs=market_inputs,
        references=references,
        hybrid_weight=fitted_weight,
    )
    scores, paired, point_deltas = evaluation.compute_losses(evaluation_rows)
    bootstrap = evaluation.race_bootstrap(evaluation_rows, paired)
    evaluation.assert_frozen(scores, point_deltas, bootstrap)
    evaluation_report = {
        "n_observations": len(evaluation_rows),
        "n_races": len({row["state"] for row in evaluation_rows}),
        "horizon_counts": {
            str(horizon): sum(
                row["horizon_days"] == horizon for row in evaluation_rows
            )
            for horizon in HORIZONS
        },
        "scores": scores,
        "paired_equal_horizon_delta": point_deltas,
        "bootstrap": bootstrap,
        "frozen_audit_verified": True,
    }
    diagnostics = presentation_diagnostics(evaluation_rows)
    if diagnostics["favored_party_agreement_count"] != 58:
        raise AssertionError("Frozen favored-party agreement changed")
    if diagnostics["favored_party_disagreements"] != [
        "2024-ohio-14d", "2024-ohio-7d"
    ]:
        raise AssertionError("Frozen favored-party disagreements changed")

    report = {
        "schema_version": 1,
        "pipeline": {
            "name": "senate_polling_prediction_markets_end_to_end",
            "market_mode": market_report["mode"],
            "stages": [
                "poll_level_weighting",
                "historical_calibration",
                "polling_forecasts_2022_2024",
                "hybrid_fit_2022",
                "locked_spec_evaluation_2024",
                "race_cluster_bootstrap_2024",
                "presentation_outputs",
            ],
        },
        "upstream": {
            "polling": polling_report,
            "market": market_report,
        },
        "development_2022": development_report,
        "evaluation_2024": evaluation_report,
        "presentation_diagnostics_2024": diagnostics,
        "checks": {
            "polling_forecasts_rebuilt": len(polling_forecasts) == 98,
            "development_rows_joined": len(development_rows) == 34,
            "evaluation_rows_joined": len(evaluation_rows) == 60,
            "georgia_runoff_rows_in_fit": 0,
            "frozen_polling_weight": fitted_weight,
            "hybrid_equals_market_2024": scores["hybrid"] == scores["market"],
            "all_frozen_regressions_passed": True,
        },
    }

    if output_dir is not None:
        presentation.write_outputs(
            output_dir=output_dir,
            polling_forecasts=polling_forecasts,
            market_inputs=market_inputs,
            development_rows=development_rows,
            evaluation_rows=evaluation_rows,
            report=report,
            include_rebuilt_market_table=rebuild_markets,
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Root for generated tables and figures (default: outputs)",
    )
    parser.add_argument(
        "--rebuild-markets",
        action="store_true",
        help="Reacquire and reconstruct checksum-pinned raw market sources",
    )
    parser.add_argument("--market-manifest", type=Path, default=markets.DEFAULT_MANIFEST)
    parser.add_argument("--market-cache-dir", type=Path, default=markets.DEFAULT_CACHE)
    parser.add_argument(
        "--market-offline",
        action="store_true",
        help="With --rebuild-markets, use only verified cache/local files",
    )
    parser.add_argument(
        "--source-2022-root",
        type=Path,
        help="With --rebuild-markets, optional local pinned 2022 checkout",
    )
    parser.add_argument(
        "--source-2024-json",
        type=Path,
        help="With --rebuild-markets, optional local pinned 2024 JSON",
    )
    args = parser.parse_args()

    market_specific = (
        args.market_offline
        or args.source_2022_root is not None
        or args.source_2024_json is not None
        or args.market_manifest != markets.DEFAULT_MANIFEST
        or args.market_cache_dir != markets.DEFAULT_CACHE
    )
    if market_specific and not args.rebuild_markets:
        parser.error("market-source options require --rebuild-markets")

    report = run(
        output_dir=args.output_dir,
        rebuild_markets=args.rebuild_markets,
        market_manifest=args.market_manifest,
        market_cache_dir=args.market_cache_dir,
        market_offline=args.market_offline,
        source_2022_root=args.source_2022_root,
        source_2024_json=args.source_2024_json,
    )
    summary = {
        "status": "ok",
        "market_mode": report["pipeline"]["market_mode"],
        "w_unconstrained": report["development_2022"]["fit"]["w_unconstrained"],
        "w_constrained": report["development_2022"]["fit"]["w_constrained"],
        "2024_delta_brier_poll_minus_market": report["evaluation_2024"]
        ["paired_equal_horizon_delta"]["brier"],
        "2024_delta_log_loss_poll_minus_market": report["evaluation_2024"]
        ["paired_equal_horizon_delta"]["log_loss"],
        "artifacts": report.get("artifacts", []),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
