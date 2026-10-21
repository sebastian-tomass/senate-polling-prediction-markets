# Senate Polling vs. Prediction Markets

A forecasting project asking whether polling-based probabilities and prediction-market probabilities can be meaningfully combined to improve U.S. Senate election forecasts.

## Research question

**Can a quality-weighted polling model and prediction-market probabilities be combined to produce better Senate election forecasts than either source alone?**

The project builds an independent polling model, compares it with prediction-market probabilities at fixed pre-election horizons, and fits a simple convex ensemble:

```text
p_hybrid = w * p_poll + (1 - w) * p_market
```

The combination weight is estimated on 2022 Senate races and then held fixed for a locked-spec retrospective evaluation on 2024 races. The final specification is intended to be carried forward to a prospective 2026 evaluation.

## Headline result

The fitted 2022 hybrid placed **zero constrained weight on polling**:

- unconstrained polling weight: **-0.337**
- constrained polling weight: **0.000**

So the frozen hybrid forecast is identical to the prediction-market forecast.

In the locked-spec 2024 evaluation, the prediction-market probabilities had lower point-estimate Brier score and log loss than the polling model:

| Model | Equal-horizon Brier | Equal-horizon log loss |
| --- | ---: | ---: |
| Polling model | 0.087484 | 0.283330 |
| Prediction market | 0.076103 | 0.268463 |
| Frozen hybrid | 0.076103 | 0.268463 |

Polling-minus-market paired differences:

- **Δ Brier:** +0.011381
- **Δ log loss:** +0.014867

Positive values mean the market had lower loss.

However, uncertainty is substantial. A 50,000-replicate whole-race clustered bootstrap gave:

- Δ Brier 95% percentile interval: **[-0.011233, 0.035584]**
- Δ log-loss 95% percentile interval: **[-0.043708, 0.072087]**

Both intervals include zero, so the magnitude—and even sign—of the aggregate advantage is estimated imprecisely.

## Run the complete reproduction

The final pipeline connects every analytical stage and creates the presentation tables and figures:

```bash
python -m pip install -r requirements.txt
python src/run_pipeline.py
```

The default command is deterministic and offline. It reconstructs all polling inputs from the committed poll rows, repeats the 2022 fit and 2024 scoring/bootstrap, verifies every frozen result, and writes the generated artifacts under `outputs/`. The market probabilities in the committed common-support tables were independently rebuilt in the preceding market-provenance stage.

To reacquire and reprocess the checksum-pinned raw market archives in the same run:

```bash
python src/run_pipeline.py --rebuild-markets
```

Neither upstream market source contains a license file, so raw files are verified in the gitignored cache and are not redistributed. See the [final results and reproducibility guide](docs/results.md) and [generated-output inventory](outputs/README.md).

GitHub Actions runs the full regression suite and the offline end-to-end command on every push and pull request, then retains the generated tables and figures as a workflow artifact.

## Reproduce the 2022 and 2024 polling forecasts

The [polling-forecast pipeline](src/generate_polling_forecasts.py) now connects the upstream reconstruction stages: it rebuilds poll-level weights and race–horizon margins, substitutes those rebuilt 2006–2020 margins into the historical calibration, and converts the 2022/2024 margins into Democratic win probabilities:

```bash
python src/generate_polling_forecasts.py
python src/generate_polling_forecasts.py \
  --csv outputs/tables/rebuilt_polling_forecasts.csv
python -m unittest discover -s tests -v
```

The script generates **98 forecasts**: 38 for 2022 and 60 for 2024. The four Georgia 2022 post-general-runoff observations remain robustness-only, leaving the original 34-row PRIMARY development sample unchanged. All 94 committed common-support probabilities match the independently regenerated values to floating-point precision, as do the committed 2024 margins. Market prices and 2022/2024 outcomes are not used to construct any polling forecast.

## Reproduce the prediction-market probabilities

The [market-source manifest](data/raw/market_sources.json) and [market reconstruction script](src/reconstruct_market_probabilities.py) rebuild the market side of the same **94 PRIMARY common-support observations** from checksum-pinned upstream archives:

```bash
python src/reconstruct_market_probabilities.py
python src/reconstruct_market_probabilities.py \
  --csv outputs/tables/rebuilt_market_probabilities.csv \
  --json outputs/tables/rebuilt_market_probabilities_audit.json
```

The first run retrieves ten 2022 trade CSVs and one 2024 CLOB-history JSON file into the gitignored `.cache/market_sources/` directory. Every file must match its pinned Git blob SHA before parsing.

- **2022:** parse 6,779 archived trades, treat the source's timezone-naive timestamps as UTC, choose the last trade at or before each noon UTC target, break timestamp ties by first source row, and convert contract-side prices to Democratic probabilities.
- **2024:** validate all 13,966 points in the 33-state archived CLOB response, then select the point nearest each scheduled noon UTC grid target. Every selected point is 2 or 3 seconds after the target and within the fail-closed 60-second tolerance.

The 34 reconstructed 2022 probabilities and 60 reconstructed 2024 probabilities match the committed common-support values within floating-point precision. Georgia's four 2022 runoff observations remain outside the PRIMARY development market sample.

Neither pinned upstream source tree contains a license file. The repository therefore includes retrieval metadata and transformations but does not redistribute the raw archives. See the [raw-source retrieval and redistribution note](data/raw/README.md), including offline local-checkout instructions.

## Reproduce poll-level weighting and polling margins

The [frozen eligible poll usages](data/processed/README.md#poll-level-weighting-pipeline-frozen-20062024) and [poll-level weighting script](src/reconstruct_poll_weights.py) reconstruct the final weighted Democratic-minus-Republican Senate polling margins across **2006–2024**:

```bash
python src/reconstruct_poll_weights.py
python src/reconstruct_poll_weights.py \
  --rows-csv outputs/tables/rebuilt_poll_weights.csv \
  --signals-csv outputs/tables/rebuilt_polling_signals.csv
python -m unittest discover -s tests -v
```

The script regenerates **7,346 poll-usage weights** and **629 race×horizon signals** using the frozen recency, sample-size and original-pollster repeat-bin rules, then applies the vintage-safe quality multipliers computed by the preceding quality module. The recreated margins and weight totals match all frozen audit reference values to floating-point precision. **Eligibility and documented pollster identity mappings are fixed inputs**; poll inclusion is not reconsidered here. Known reversed-date source records are retained and explicitly documented.

## Reproduce vintage-safe pollster quality

The [frozen historical poll-level error inputs](data/processed/historical_reliability_errors.csv) and [quality reconstruction script](src/reconstruct_pollster_quality.py) reproduce prior-cycle pollster MAE histories, fixed `K=18` shrinkage, and the squared reliability multipliers with **no clamping**. Each forecast vintage uses only **earlier election cycles**.

```bash
python src/reconstruct_pollster_quality.py
python src/reconstruct_pollster_quality.py --csv outputs/tables/pollster_quality.csv
python -m unittest discover -s tests -v
```

The 1,005 frozen eligible reliability-error records reproduce all **2,729 pollster–vintage audit entries**, including the 2022/2024 vintages, within `1e-12`. A missing history receives `q=1`. See the [quality-source provenance and stage boundary](data/processed/README.md#vintage-safe-pollster-reliability-and-quality). The later poll-level pipeline will independently rebuild the polling signal weights using these multipliers.

## Reproduce historical polling calibration (2006–2020)

The [531 frozen historical polling signals](data/processed/2006_2020_polling_signals.csv) and [calibration script](src/calibrate_polling_2006_2020.py) reproduce the **527-observation PRIMARY** polling-error calibration, with Georgia 2008 runoff records excluded:

```bash
python src/calibrate_polling_2006_2020.py
python -m unittest discover -s tests -v
```

The script independently calculates horizon-specific historical-error means and sample standard deviations (60, 30, 14 and 7 days) from the frozen margins and certified outcomes, then regression-checks them against the audit. The downstream polling-forecast pipeline additionally substitutes the Step 3 poll-level reconstructions for those historical margins before recalibrating. See the [historical data lineage and stage boundary](data/processed/README.md#20062020-historical-polling-calibration).

## Reproduce the 2022 development fit

The [34-observation 2022 development dataset](data/processed/2022_common_support.csv) and [hybrid-fit script](src/fit_hybrid_2022.py) reproduce how the single global convex-combination weight was obtained. Georgia's post-general-runoff robustness observations are excluded, and each of the four horizons contributes exactly 25% of the Brier fitting objective.

```bash
python -m pip install -r requirements.txt
python src/fit_hybrid_2022.py
python -m unittest discover -s tests -v
```

The unconstrained polling weight is **−0.337005**; applying the frozen 0–1 constraint gives **w = 0**, so the frozen ensemble equals the market. The script also reproduces the horizon-specific and equal-horizon polling/market Brier and log-loss results without recalculating input forecasts. See the [2022 data provenance notes](data/processed/README.md#2022-development-common-support-data).

## Reproduce the 2024 results

The [processed common-support dataset](data/processed/2024_common_support.csv) and [evaluation script](src/evaluate_2024.py) reproduce the headline Brier scores, log losses, and 50,000-draw race-cluster bootstrap directly from the frozen forecast observations:

```bash
python -m pip install -r requirements.txt
python src/evaluate_2024.py
python -m unittest discover -s tests -v
```

See [the data provenance and reproduction guide](data/processed/README.md) for the fixed sample, archived sources, and validation checks.

## Why the result is interesting

Polling and market forecasts were highly overlapping in 2024:

- favored-party agreement: **58 / 60 (96.7%)**
- probability correlation: **0.973**
- logit correlation: **0.904**

That means the comparison is mostly about **how much probability to assign to the same likely winner**, rather than frequent disagreement over which party is favored.

The strongest supported conclusion is therefore not that polling is useless. It is that, **within this forecasting architecture and sample, adding the polling probability to the market probability did not improve the frozen convex ensemble**.

## Polling model

The polling model uses:

- fixed horizons of **60, 30, 14, and 7 days** before Election Day;
- recency weighting;
- square-root sample-size weighting;
- repeat-pollster dilution;
- vintage-safe pollster reliability weights;
- historical Senate polling-error calibration from **2006–2020**.

Pollster quality is estimated using prior-cycle information only. Historical pollster MAE is shrunk toward the contemporaneous global MAE with (K=18):

```text
shrunk_MAE =
    (n / (n + 18)) * raw_prior_MAE
  + (18 / (n + 18)) * prior_global_MAE
```

The frozen quality multiplier is:

```text
q = (prior_global_MAE / shrunk_MAE)^2
```

Pollsters with no eligible prior history receive a neutral multiplier of 1.

The quality multiplier is applied to the otherwise frozen polling weight:

```text
w_poll = w_recency * w_sample * w_repeat * q
```

Historical polling errors are then used to translate each weighted D-minus-R polling margin into a Democratic win probability.

See [docs/methodology.md](docs/methodology.md) for the full specification.

## Evaluation design

The final project uses three analytical stages plus one prospective test:

**Historical calibration (2006–2020)**  
Construct and calibrate the polling model using historical Senate polling errors.

**Development (2022)**  
Fit one global poll/market convex-combination weight using an equal-horizon Brier objective.

**Locked-spec retrospective evaluation (2024)**  
Evaluate the already-fixed 2022 combination rule and final polling specification. Because the final polling methodology was developed iteratively after earlier inspection of 2024-era results, 2024 is not described as pristine prospective validation.

**Prospective test (2026)**  
Freeze the methodology before the 2026 Senate election and evaluate it prospectively.

## Repository status

The retrospective statistical analysis and its six-step GitHub implementation are complete. The repository now reproduces the frozen 2006–2024 workflow from poll rows through calibration, forecasts, hybrid fitting, scoring, clustered inference, tables, and figures.

Implemented components include:

- processed modeling datasets;
- scripts for polling aggregation, calibration, market processing, hybrid fitting, and scoring;
- one end-to-end reproduction command;
- reproducible tables and figures;
- methodology and data-provenance documentation;
- automated regression tests and continuous integration.

The next research stage is to freeze and run the prospective 2026 forecasting application before observing its election outcomes.

## Repository structure

```text
.
├── .github/workflows/ci.yml
├── README.md
├── data/
│   ├── raw/
│   │   ├── README.md
│   │   └── market_sources.json
│   └── processed/
│       └── README.md
├── docs/
│   ├── data_sources.md
│   ├── methodology.md
│   └── results.md
├── notebooks/
│   └── README.md
├── outputs/
│   ├── README.md
│   ├── figures/
│   └── tables/
├── src/
│   ├── README.md
│   ├── build_presentation.py
│   ├── run_pipeline.py
│   └── stage-specific modules
├── tests/
└── archive/
    └── README.md
```

## Interpretation

The project does **not** establish that polling contains no predictive information, nor does it directly identify a causal or independent information channel from polling into prediction-market prices.

It does show that:

1. a historically calibrated, quality-weighted polling model and prediction-market probabilities are strongly associated;
2. the 2022 development fit assigned no positive convex-combination weight to polling;
3. 2024 market probabilities had lower point-estimate probabilistic losses than the polling model at every horizon;
4. the 18-race 2024 sample is too small to estimate the aggregate market advantage precisely.

The natural next research question is whether the part of market prices that cannot be explained by polling contains incremental predictive information.

## License

A license has not yet been selected.
