# Methodology

This document describes the final forecasting specification. Earlier experimental versions are not part of the main presentation.

## 1. Forecast horizons

Forecasts are constructed at four fixed horizons before Election Day:

- 60 days
- 30 days
- 14 days
- 7 days

Polling and market forecasts are aligned to the same target horizons.

## 2. Polling signal

For each race (i) and horizon (h), the polling signal is a weighted Democratic-minus-Republican margin:

```text
m_poll(i,h) = sum_j(w_j * m_j) / sum_j(w_j)
```

where (m_j) is poll (j)'s Democratic-minus-Republican margin.

### Recency

Poll age is based on the median field date.

```text
w_recency = 2^(-age / (14 + 0.2*h))
```

### Sample size

Sample size receives diminishing-return square-root weighting. Missing sample size uses the frozen fallback (n=600). The final reconstruction preserves the frozen sample-size cap used by the project.

### Repeat-pollster adjustment

Repeated surveys by the same original polling identity are diluted using fixed, non-overlapping 14-day bins so that one pollster cannot dominate an average simply by releasing many closely spaced polls.

### Pollster quality

Pollster quality is vintage-safe: a forecast in cycle (t) may use reliability evidence only from elections completed before (t).

Reliability is estimated from eligible historical Senate polls close to Election Day. For pollster (j):

```text
shrunk_MAE_j =
    (n_j / (n_j + 18)) * raw_prior_MAE_j
  + (18 / (n_j + 18)) * prior_global_MAE
```

The frozen quality multiplier is:

```text
q_j = (prior_global_MAE / shrunk_MAE_j)^2
```

A pollster with no eligible prior history receives (q_j=1).

The final row weight is:

```text
w_j = w_recency * w_sample * w_repeat * q_j
```

No quality-multiplier clamping is used.

## 3. Historical calibration

The historical polling model is calibrated on U.S. Senate races from 2006–2020.

For each historical race-horizon observation:

```text
error(i,h) = actual_margin_i - polling_margin(i,h)
```

For each horizon:

```text
error_h ~ Normal(mu_h, sigma_h^2)
```

The primary calibration sample contains 527 race-horizon observations. A post-general runoff case is retained separately as procedural robustness rather than mixed into the primary calibration.

The polling probability is:

```text
p_poll(i,h) = Phi((polling_margin(i,h) + mu_h) / sigma_h)
```

where `Phi` is the standard normal CDF.

## 4. Prediction-market forecast

Prediction-market probabilities are sampled at the same 60/30/14/7-day horizons and expressed as Democratic win probabilities.

The project preserves the frozen market extraction rules used in the audit pipeline rather than re-estimating or smoothing market prices during model fitting.

## 5. Hybrid model

The combined forecast is intentionally simple:

```text
p_hybrid = w * p_poll + (1 - w) * p_market
```

A single global (w) is fitted on the 2022 development sample.

The objective is equal-horizon average Brier score, so each horizon receives 25% of the fitting objective even though the number of observations differs across horizons.

The unconstrained optimum is approximately:

```text
w = -0.337
```

After imposing:

```text
0 <= w <= 1
```

the frozen weight is:

```text
w = 0
```

Thus the final frozen hybrid equals the market forecast.

## 6. 2024 evaluation

The locked-spec 2024 common-support dataset contains:

- 60 race-horizon observations
- 18 distinct Senate races
- 12 observations at 60 days
- 17 at 30 days
- 15 at 14 days
- 16 at 7 days

Primary scoring uses equal-horizon averages of Brier score and log loss.

The polling-minus-market paired differences are defined so that positive values mean lower market loss.

### Primary point estimates

| Metric | Polling | Market | Difference (poll - market) |
| --- | ---: | ---: | ---: |
| Equal-horizon Brier | 0.087484 | 0.076103 | +0.011381 |
| Equal-horizon log loss | 0.283330 | 0.268463 | +0.014867 |

### Clustered uncertainty

Uncertainty is estimated by resampling whole races with replacement:

- 18 race clusters
- all horizons for a sampled race travel together
- 50,000 replicates
- seed 2026
- NumPy PCG64
- simple 95% percentile intervals

Results:

| Quantity | Point estimate | 95% interval |
| --- | ---: | ---: |
| Δ Brier | +0.011381 | [-0.011233, 0.035584] |
| Δ log loss | +0.014867 | [-0.043708, 0.072087] |

The intervals include zero, so the aggregate advantage is not precisely estimated.

## 7. Poll-market overlap

In the 2024 common-support sample:

- 58 of 60 observations agree on the favored party;
- probability correlation is about 0.973;
- logit correlation is about 0.904.

The comparison is therefore largely about calibration and confidence rather than frequent disagreement over the likely winner.

## 8. Known source-data sensitivity

One malformed Arizona polling record has reversed start/end dates. It is retained in the primary specification solely to preserve exact comparability with the frozen polling universe.

A pre-specified exclusion sensitivity changes the aggregate polling-minus-market differences only slightly:

- Δ Brier: +0.011381 to +0.011321
- Δ log loss: +0.014867 to +0.014654

The source-data anomaly does not materially drive the conclusion.

## 9. Status of the evidence

The final specification was developed iteratively using historical data and retrospective diagnostics through 2024. Accordingly, 2024 is presented as a locked-spec retrospective evaluation rather than pristine prospective validation.

The planned 2026 application is the prospective test of the finalized methodology.
