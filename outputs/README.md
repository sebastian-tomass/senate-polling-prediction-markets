# Generated outputs

Run the complete offline reproduction from the repository root:

```bash
python src/run_pipeline.py
```

The command replaces the contents generated under `outputs/tables/` and
`outputs/figures/`. Those artifacts are gitignored because every file is
deterministically recreated from versioned inputs and code.

## Tables

- `end_to_end_audit.json`: nested audit record for every pipeline stage and
  frozen regression check.
- `rebuilt_polling_forecasts.csv`: all 98 reconstructed 2022/2024 polling
  forecasts, including four Georgia runoff-robustness rows.
- `analysis_common_support_2022.csv`: the 34-row development join actually
  passed to the hybrid fit.
- `analysis_common_support_2024.csv`: the 60-row locked-spec evaluation join.
- `calibration_parameters.csv`: horizon-specific historical calibration.
- `headline_results.csv`: compact presentation table with the central
  estimates and bootstrap intervals.
- `scores_by_horizon.csv`: 2022 and 2024 model scores by horizon, plus
  equal-horizon and pooled summaries.
- `bootstrap_intervals.csv`: the fixed 50,000-replicate race-cluster results.
- `rebuilt_market_probabilities.csv`: added only when the command runs with
  `--rebuild-markets`.

## Figures

Each final figure is written as both PNG and SVG:

- `2022_hybrid_weight_objective`: the equal-horizon development objective and
  constrained boundary solution.
- `2024_scores_by_horizon`: polling and market/hybrid Brier and log losses.
- `2024_poll_market_probabilities`: the 60 paired probabilities, certified
  winners, and the two favorite-party disagreements.

GitHub Actions runs the same offline command on every push and pull request and
retains the generated directory as a workflow artifact.
