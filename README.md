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

The statistical analysis is complete. This repository is being converted from an extensive audit workbook into a cleaner reproducible research pipeline.

Planned repository components include:

- processed modeling datasets;
- scripts for polling aggregation, calibration, market processing, and scoring;
- reproducible tables and figures;
- methodology and data-provenance documentation;
- the frozen 2026 prospective forecasting pipeline.

## Repository structure

```text
.
├── README.md
├── data/
│   └── README.md
├── docs/
│   ├── data_sources.md
│   └── methodology.md
├── notebooks/
│   └── README.md
├── outputs/
│   ├── figures/
│   └── tables/
├── src/
│   └── README.md
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
