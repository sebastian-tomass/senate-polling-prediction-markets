"""Reproduce frozen 2024 Senate polling/market scores and race-cluster bootstrap.

Run from the repository root: python src/evaluate_2024.py
No forecasts, models, or weights are fitted in this script.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import numpy as np

HORIZONS = (60, 30, 14, 7)
N_BY_HORIZON = (12, 17, 15, 16)
N_REPLICATES = 50_000
SEED = 2026
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/processed/2024_common_support.csv"

# Full-precision immutable regression targets, read from the frozen audit workbook.
FROZEN = {
    "poll_equal_brier": .08748401164864145,
    "poll_equal_log_loss": .28333000509283224,
    "market_equal_brier": .07610306881127452,
    "market_equal_log_loss": .26846257428218,
    "delta_equal_brier": .011380942837366929,
    "delta_equal_log_loss": .014867430810652177,
    "poll_pooled_brier": .08539303443176488,
    "poll_pooled_log_loss": .27651634926090024,
    "market_pooled_brier": .07423225416666666,
    "market_pooled_log_loss": .2627391680812184,
    "bootstrap_brier_mean": .011408487461012206,
    "bootstrap_brier_sd": .011903568037010117,
    "bootstrap_brier_lower": -.01123307894190075,
    "bootstrap_brier_upper": .0355836706914058,
    "bootstrap_ll_mean": .01497359254329594,
    "bootstrap_ll_sd": .029503234813694646,
    "bootstrap_ll_lower": -.043708318185292014,
    "bootstrap_ll_upper": .07208673274929539,
    "bootstrap_brier_positive_fraction": .83312,
    "bootstrap_ll_positive_fraction": .69674,
}


def load_data(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"polling_signal_id", "state", "horizon_days", "p_poll_dem",
                    "p_market_dem", "p_hybrid_dem", "y_dem_win", "source_data_anomaly_present"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV missing required columns")
        rows = list(reader)
    ids = [r["polling_signal_id"] for r in rows]
    if len(rows) != 60 or len(set(ids)) != 60:
        raise ValueError("Expected exactly 60 unique race-horizon rows")
    if len({r["state"].lower() for r in rows}) != 18:
        raise ValueError("Expected 18 distinct Senate races")
    if tuple(sum(int(r["horizon_days"]) == h for r in rows) for h in HORIZONS) != N_BY_HORIZON:
        raise ValueError("Frozen horizon counts changed")
    anomalies = {r["polling_signal_id"] for r in rows if r["source_data_anomaly_present"] == "true"}
    if anomalies != {"2024-arizona-14d", "2024-arizona-7d"}:
        raise ValueError("Frozen Arizona anomalies changed")
    for r in rows:
        if r["source_data_anomaly_present"] not in ("true", "false") or int(r["y_dem_win"]) not in (0, 1):
            raise ValueError("Invalid anomaly flag or outcome")
        for key in ("p_poll_dem", "p_market_dem", "p_hybrid_dem"):
            p = float(r[key])
            if not np.isfinite(p) or not 0 < p < 1:
                raise ValueError(f"Invalid probability {key} for {r['polling_signal_id']}")
        if float(r["p_hybrid_dem"]) != float(r["p_market_dem"]):
            raise ValueError("Frozen hybrid must equal the market (w=0)")
    return rows


def compute_losses(rows: list[dict]):
    y = np.array([int(r["y_dem_win"]) for r in rows], dtype=float)
    h = np.array([int(r["horizon_days"]) for r in rows])
    losses, scores = {}, {}
    for model, field in (("polling", "p_poll_dem"), ("market", "p_market_dem"), ("hybrid", "p_hybrid_dem")):
        p = np.array([float(r[field]) for r in rows])
        bs = (p - y)**2
        ll = -(y * np.log(p) + (1-y)*np.log1p(-p))
        correct = ((p >= .5) == (y == 1))
        losses[model] = {"brier": bs, "log_loss": ll}
        by_h = {str(t): {"n": int((h == t).sum()), "brier": float(bs[h == t].mean()),
                         "log_loss": float(ll[h == t].mean()), "accuracy": float(correct[h == t].mean())}
                for t in HORIZONS}
        scores[model] = {
            "by_horizon": by_h,
            "equal_horizon": {metric: float(np.mean([by_h[str(t)][metric] for t in HORIZONS]))
                              for metric in ("brier", "log_loss")},
            "pooled": {"brier": float(bs.mean()), "log_loss": float(ll.mean()),
                       "accuracy": float(correct.mean())},
        }
    if scores["hybrid"] != scores["market"]:
        raise AssertionError("Hybrid/market metrics differ")
    paired = {metric: losses["polling"][metric]-losses["market"][metric]
              for metric in ("brier", "log_loss")}
    points = {name: float(np.mean([values[h == t].mean() for t in HORIZONS]))
              for name, values in paired.items()}
    return scores, paired, points


def race_bootstrap(rows: list[dict], paired: dict, *, n_replicates=N_REPLICATES, seed=SEED):
    races = sorted({r["state"].lower() for r in rows})
    horizons = np.array([int(r["horizon_days"]) for r in rows])
    state = np.array([r["state"].lower() for r in rows])
    counts = np.zeros((len(races), len(HORIZONS)), dtype=int)
    sums = {name: np.zeros(counts.shape) for name in paired}
    for i, race in enumerate(races):
        for j, horizon in enumerate(HORIZONS):
            mask = (state == race) & (horizons == horizon)
            counts[i, j] = mask.sum()
            for name, values in paired.items():
                sums[name][i, j] = values[mask].sum()
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.integers(0, len(races), size=(n_replicates, len(races)))
    first_code = ''.join('0123456789ABCDEFGH'[int(i)] for i in draws[0])
    sampled_counts = counts[draws].sum(axis=1)
    empty = int(np.any(sampled_counts == 0, axis=1).sum())
    if empty:
        raise RuntimeError(f"{empty} empty-horizon draws; no discards or redraws allowed")
    results = {}
    for name, arr in sums.items():
        deltas = (arr[draws].sum(axis=1) / sampled_counts).mean(axis=1)
        lo, hi = np.percentile(deltas, [2.5, 97.5])
        results[f"delta_{name}"] = {
            "bootstrap_mean": float(deltas.mean()), "bootstrap_sd": float(deltas.std(ddof=1)),
            "ci_2_5": float(lo), "ci_97_5": float(hi),
            "fraction_positive_descriptive": float((deltas > 0).mean()),
        }
    return {"n_races": 18, "n_replicates": n_replicates, "seed": seed,
            "rng": "numpy.PCG64", "first_race_draw_code": first_code,
            "valid_replicates": n_replicates, "empty_horizon_replicates": empty,
            "discarded_or_redrawn": 0, "horizon_weight_each": .25, **results}


def assert_frozen(scores: dict, points: dict, bootstrap: dict, tol=1e-12):
    values = {}
    for key, model in (("poll", "polling"), ("market", "market")):
        for metric in ("brier", "log_loss"):
            values[f"{key}_equal_{metric}"] = scores[model]["equal_horizon"][metric]
            values[f"{key}_pooled_{metric}"] = scores[model]["pooled"][metric]
    values.update({f"delta_equal_{k}": v for k, v in points.items()})
    for suffix, metric in (("brier", "brier"), ("ll", "log_loss")):
        res = bootstrap[f"delta_{metric}"]
        for name, field in (("mean", "bootstrap_mean"), ("sd", "bootstrap_sd"),
                            ("lower", "ci_2_5"), ("upper", "ci_97_5"),
                            ("positive_fraction", "fraction_positive_descriptive")):
            values[f"bootstrap_{suffix}_{name}"] = res[field]
    bad = {key: (reference, values[key]) for key, reference in FROZEN.items()
           if abs(reference - values[key]) > tol}
    if bad:
        raise AssertionError(f"Mismatch with frozen authoritative results: {bad}")
    if bootstrap["first_race_draw_code"] != "F30B6816B6EECGC3FB":
        raise AssertionError("PCG64 race sampling stream changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--json", type=Path, help="Optionally write the report to JSON")
    args = parser.parse_args()
    rows = load_data(args.data)
    scores, paired, point_deltas = compute_losses(rows)
    bootstrap = race_bootstrap(rows, paired)
    assert_frozen(scores, point_deltas, bootstrap)
    report = {"n_observations": 60, "n_races": 18,
              "horizon_counts": dict(zip(map(str, HORIZONS), N_BY_HORIZON)),
              "scores": scores, "paired_equal_horizon_delta": point_deltas,
              "bootstrap": bootstrap, "frozen_audit_verified": True}
    output = json.dumps(report, indent=2) + "\n"
    print(output, end="")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
