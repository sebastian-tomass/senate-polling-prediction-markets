"""Write final audit tables and figures for the end-to-end reproduction."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import reconstruct_market_probabilities as markets  # noqa: E402


HORIZONS = (60, 30, 14, 7)
DEVELOPMENT_FIELDS = (
    "polling_signal_id",
    "state",
    "horizon_days",
    "cutoff_date",
    "sample_status",
    "p_poll_dem",
    "p_market_dem",
    "y_dem_win",
)
EVALUATION_FIELDS = (
    "polling_signal_id",
    "state",
    "horizon_days",
    "cutoff_date",
    "p_poll_dem",
    "p_market_dem",
    "p_hybrid_dem",
    "y_dem_win",
    "poll_weighted_margin",
    "source_data_anomaly_present",
)


def _write_csv(path: Path, rows: list[dict], fields: tuple[str, ...] | list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _headline_rows(report: dict) -> list[dict]:
    fit = report["development_2022"]["fit"]
    scores = report["evaluation_2024"]["scores"]
    points = report["evaluation_2024"]["paired_equal_horizon_delta"]
    bootstrap = report["evaluation_2024"]["bootstrap"]
    diagnostics = report["presentation_diagnostics_2024"]
    return [
        {
            "stage": "2022 development",
            "metric": "Unconstrained polling weight",
            "estimate": fit["w_unconstrained"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Equal-horizon Brier objective",
        },
        {
            "stage": "2022 development",
            "metric": "Constrained polling weight",
            "estimate": fit["w_constrained"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Constrained to [0, 1]",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Polling equal-horizon Brier",
            "estimate": scores["polling"]["equal_horizon"]["brier"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Lower is better",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Market / hybrid equal-horizon Brier",
            "estimate": scores["market"]["equal_horizon"]["brier"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Frozen hybrid equals market at w=0",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Polling minus market Brier",
            "estimate": points["brier"],
            "ci_2_5": bootstrap["delta_brier"]["ci_2_5"],
            "ci_97_5": bootstrap["delta_brier"]["ci_97_5"],
            "notes": "Positive values favor the market",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Polling equal-horizon log loss",
            "estimate": scores["polling"]["equal_horizon"]["log_loss"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Lower is better",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Market / hybrid equal-horizon log loss",
            "estimate": scores["market"]["equal_horizon"]["log_loss"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Frozen hybrid equals market at w=0",
        },
        {
            "stage": "2024 evaluation",
            "metric": "Polling minus market log loss",
            "estimate": points["log_loss"],
            "ci_2_5": bootstrap["delta_log_loss"]["ci_2_5"],
            "ci_97_5": bootstrap["delta_log_loss"]["ci_97_5"],
            "notes": "Positive values favor the market",
        },
        {
            "stage": "2024 comparison",
            "metric": "Favored-party agreement",
            "estimate": diagnostics["favored_party_agreement_fraction"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": (
                f"{diagnostics['favored_party_agreement_count']} of "
                f"{diagnostics['n_observations']} observations"
            ),
        },
        {
            "stage": "2024 comparison",
            "metric": "Probability correlation",
            "estimate": diagnostics["probability_correlation"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Pearson correlation",
        },
        {
            "stage": "2024 comparison",
            "metric": "Logit correlation",
            "estimate": diagnostics["logit_correlation"],
            "ci_2_5": "",
            "ci_97_5": "",
            "notes": "Pearson correlation after logit transform",
        },
    ]


def _score_rows(report: dict) -> list[dict]:
    rows = []
    for cycle, section in (
        (2022, report["development_2022"]),
        (2024, report["evaluation_2024"]),
    ):
        observation_count = (
            section["sample"]["n_primary"]
            if cycle == 2022
            else section["n_observations"]
        )
        for model in ("polling", "market", "hybrid"):
            scores = section["scores"][model]
            for horizon in HORIZONS:
                observed = scores["by_horizon"][str(horizon)]
                rows.append({
                    "cycle": cycle,
                    "model": model,
                    "aggregation": "horizon",
                    "horizon_days": horizon,
                    **observed,
                })
            rows.append({
                "cycle": cycle,
                "model": model,
                "aggregation": "equal_horizon",
                "horizon_days": "",
                "n": observation_count,
                "brier": scores["equal_horizon"]["brier"],
                "log_loss": scores["equal_horizon"]["log_loss"],
                "accuracy": "",
            })
            rows.append({
                "cycle": cycle,
                "model": model,
                "aggregation": "pooled",
                "horizon_days": "",
                "n": observation_count,
                **scores["pooled"],
            })
    return rows


def _bootstrap_rows(report: dict) -> list[dict]:
    bootstrap = report["evaluation_2024"]["bootstrap"]
    return [
        {
            "metric": metric,
            **bootstrap[f"delta_{key}"],
            "n_replicates": bootstrap["n_replicates"],
            "n_races": bootstrap["n_races"],
            "seed": bootstrap["seed"],
            "rng": bootstrap["rng"],
        }
        for metric, key in (("Brier", "brier"), ("Log loss", "log_loss"))
    ]


def _calibration_rows(report: dict) -> list[dict]:
    parameters = report["upstream"]["polling"]["historical_calibration"]["parameters"]
    return [
        {"horizon_days": horizon, **parameters[str(horizon)]}
        for horizon in HORIZONS
    ]


def _figure_style():
    return plt.rc_context({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def _save_figure(fig, base_path: Path) -> list[str]:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    png = base_path.with_suffix(".png")
    svg = base_path.with_suffix(".svg")
    fig.savefig(
        png,
        dpi=200,
        bbox_inches="tight",
        metadata={"Software": "senate-polling-prediction-markets"},
    )
    fig.savefig(
        svg,
        bbox_inches="tight",
        metadata={"Creator": "senate-polling-prediction-markets", "Date": None},
    )
    plt.close(fig)
    return [f"figures/{png.name}", f"figures/{svg.name}"]


def plot_2022_objective(rows: list[dict], report: dict, path: Path) -> list[str]:
    poll = np.array([float(row["p_poll_dem"]) for row in rows])
    market = np.array([float(row["p_market_dem"]) for row in rows])
    outcome = np.array([int(row["y_dem_win"]) for row in rows])
    horizon = np.array([int(row["horizon_days"]) for row in rows])
    weights = np.linspace(-0.5, 1.0, 601)
    losses = []
    for weight in weights:
        probability = weight * poll + (1.0 - weight) * market
        losses.append(np.mean([
            np.mean((probability[horizon == value] - outcome[horizon == value]) ** 2)
            for value in HORIZONS
        ]))

    fit = report["fit"]
    with _figure_style():
        fig, ax = plt.subplots(figsize=(7.4, 4.5))
        ax.axvspan(-0.5, 0.0, color="#D9D9D9", alpha=0.45, label="Outside convex domain")
        ax.plot(weights, losses, color="#0072B2", linewidth=2.2)
        unconstrained = fit["w_unconstrained"]
        constrained = fit["w_constrained"]
        unconstrained_loss = float(np.interp(unconstrained, weights, losses))
        constrained_loss = float(np.interp(constrained, weights, losses))
        ax.scatter([unconstrained], [unconstrained_loss], color="#D55E00", s=45, zorder=3)
        ax.scatter([constrained], [constrained_loss], color="#009E73", s=45, zorder=3)
        ax.annotate(
            f"Unconstrained optimum {unconstrained:.3f}",
            (unconstrained, unconstrained_loss),
            xytext=(12, 18),
            textcoords="offset points",
            ha="left",
            color="#A64600",
        )
        ax.annotate(
            "Constrained optimum 0.000",
            (constrained, constrained_loss),
            xytext=(10, 12),
            textcoords="offset points",
            color="#007A55",
        )
        ax.axvline(0.0, color="#555555", linewidth=0.9)
        ax.set_title("2022 hybrid-weight development objective", loc="left", weight="bold")
        ax.set_xlabel("Polling weight w")
        ax.set_ylabel("Equal-horizon Brier score")
        ax.set_xlim(-0.5, 1.0)
        ax.legend(frameon=False, loc="upper left")
        fig.tight_layout()
    return _save_figure(fig, path)


def plot_2024_scores(report: dict, path: Path) -> list[str]:
    scores = report["scores"]
    labels = ["60d", "30d", "14d", "7d", "Equal"]
    x = np.arange(len(labels))
    colors = {"polling": "#0072B2", "market": "#D55E00"}
    names = {"polling": "Polling", "market": "Market / frozen hybrid"}
    with _figure_style():
        fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.35))
        for axis, metric, title in (
            (axes[0], "brier", "Brier score"),
            (axes[1], "log_loss", "Log loss"),
        ):
            for model in ("polling", "market"):
                values = [
                    scores[model]["by_horizon"][str(horizon)][metric]
                    for horizon in HORIZONS
                ] + [scores[model]["equal_horizon"][metric]]
                axis.plot(
                    x,
                    values,
                    marker="o",
                    linewidth=2,
                    color=colors[model],
                    label=names[model],
                )
            axis.set_xticks(x, labels)
            axis.set_title(title, loc="left", weight="bold")
            axis.set_xlabel("Forecast horizon")
            axis.set_ylabel("Loss (lower is better)")
        axes[1].legend(frameon=False, loc="upper right")
        fig.suptitle(
            "Locked-spec 2024 forecast performance",
            x=0.065,
            ha="left",
            fontsize=13,
            fontweight="bold",
        )
        fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save_figure(fig, path)


def plot_2024_probability_comparison(
    rows: list[dict], diagnostics: dict, path: Path
) -> list[str]:
    poll = np.array([float(row["p_poll_dem"]) for row in rows])
    market = np.array([float(row["p_market_dem"]) for row in rows])
    outcomes = np.array([int(row["y_dem_win"]) for row in rows])
    with _figure_style():
        fig, ax = plt.subplots(figsize=(6.3, 5.8))
        for outcome, color, label in (
            (1, "#0072B2", "Democratic win"),
            (0, "#D55E00", "Republican win"),
        ):
            mask = outcomes == outcome
            ax.scatter(
                poll[mask],
                market[mask],
                s=38,
                alpha=0.78,
                color=color,
                edgecolor="white",
                linewidth=0.5,
                label=label,
            )
        ax.plot([0, 1], [0, 1], color="#555555", linewidth=1, linestyle="--")
        ax.axvline(0.5, color="#888888", linewidth=0.8, linestyle=":")
        ax.axhline(0.5, color="#888888", linewidth=0.8, linestyle=":")
        for row in rows:
            p_poll = float(row["p_poll_dem"])
            p_market = float(row["p_market_dem"])
            if (p_poll >= 0.5) != (p_market >= 0.5):
                ax.annotate(
                    f"{row['state']} {row['horizon_days']}d",
                    (p_poll, p_market),
                    xytext=(7, -12 if int(row["horizon_days"]) == 14 else 8),
                    textcoords="offset points",
                    fontsize=8.5,
                )
        ax.text(
            0.03,
            0.97,
            (
                f"Probability correlation = {diagnostics['probability_correlation']:.3f}\n"
                f"Favorite agreement = {diagnostics['favored_party_agreement_count']}/"
                f"{diagnostics['n_observations']}"
            ),
            transform=ax.transAxes,
            va="top",
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": "white",
                "alpha": 0.9,
                "edgecolor": "#CCCCCC",
            },
        )
        ax.set_title("Polling and market probabilities in 2024", loc="left", weight="bold")
        ax.set_xlabel("Polling probability of Democratic win")
        ax.set_ylabel("Market probability of Democratic win")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal", adjustable="box")
        ax.legend(frameon=False, loc="lower right")
        fig.tight_layout()
    return _save_figure(fig, path)


def write_outputs(
    *,
    output_dir: Path,
    polling_forecasts: list[dict],
    market_inputs: list[dict],
    development_rows: list[dict],
    evaluation_rows: list[dict],
    report: dict,
    include_rebuilt_market_table: bool,
) -> list[str]:
    """Write all machine-readable tables, the audit report, and final figures."""
    tables = output_dir / "tables"
    figures = output_dir / "figures"
    artifacts = [
        "tables/rebuilt_polling_forecasts.csv",
        "tables/analysis_common_support_2022.csv",
        "tables/analysis_common_support_2024.csv",
        "tables/calibration_parameters.csv",
        "tables/headline_results.csv",
        "tables/scores_by_horizon.csv",
        "tables/bootstrap_intervals.csv",
        "tables/end_to_end_audit.json",
    ]

    _write_csv(
        tables / "rebuilt_polling_forecasts.csv",
        polling_forecasts,
        list(polling_forecasts[0]),
    )
    _write_csv(
        tables / "analysis_common_support_2022.csv",
        development_rows,
        DEVELOPMENT_FIELDS,
    )
    _write_csv(
        tables / "analysis_common_support_2024.csv",
        evaluation_rows,
        EVALUATION_FIELDS,
    )
    _write_csv(
        tables / "calibration_parameters.csv",
        _calibration_rows(report),
        ("horizon_days", "n", "mu", "sigma", "mae"),
    )
    _write_csv(
        tables / "headline_results.csv",
        _headline_rows(report),
        ("stage", "metric", "estimate", "ci_2_5", "ci_97_5", "notes"),
    )
    _write_csv(
        tables / "scores_by_horizon.csv",
        _score_rows(report),
        (
            "cycle",
            "model",
            "aggregation",
            "horizon_days",
            "n",
            "brier",
            "log_loss",
            "accuracy",
        ),
    )
    _write_csv(
        tables / "bootstrap_intervals.csv",
        _bootstrap_rows(report),
        (
            "metric",
            "bootstrap_mean",
            "bootstrap_sd",
            "ci_2_5",
            "ci_97_5",
            "fraction_positive_descriptive",
            "n_replicates",
            "n_races",
            "seed",
            "rng",
        ),
    )

    if include_rebuilt_market_table:
        markets.export_csv(tables / "rebuilt_market_probabilities.csv", market_inputs)
        artifacts.append("tables/rebuilt_market_probabilities.csv")

    artifacts.extend(plot_2022_objective(
        development_rows,
        report["development_2022"],
        figures / "2022_hybrid_weight_objective",
    ))
    artifacts.extend(plot_2024_scores(
        report["evaluation_2024"],
        figures / "2024_scores_by_horizon",
    ))
    artifacts.extend(plot_2024_probability_comparison(
        evaluation_rows,
        report["presentation_diagnostics_2024"],
        figures / "2024_poll_market_probabilities",
    ))

    report["artifacts"] = sorted(artifacts)
    audit_path = tables / "end_to_end_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report["artifacts"]
