# Processed 2024 common-support data

`2024_common_support.csv` is an immutable, analysis-ready extract of the final 2024 Senate polling-vs-prediction-market common-support comparison.

- **60 observations** (one race × forecast horizon), **18 Senate races**.
- **Horizon counts:** 60 days = 12; 30 days = 17; 14 days = 15; 7 days = 16.
- `p_poll_dem` is the final quality-weighted, historically calibrated Democratic polling win probability; `p_market_dem` is the frozen market probability; `p_hybrid_dem` is the frozen convex ensemble probability (identical to the market because the 2022-fitted weight is zero).
- `y_dem_win` is the certified result coded 1 if the Democrat won, otherwise 0. Race names are retained in `state`, with a unique `polling_signal_id` per race × horizon.
- Probabilities are exported at **full stored precision**, not rounded for presentation.
- The two source-anomaly observations, `2024-arizona-14d` and `2024-arizona-7d`, are **retained**, with `source_data_anomaly_present=true`. This is the frozen PRIMARY specification. The erroneous source poll is `2024_senate_polls.csv` row 5, The Hill/Emerson, start 2024-10-30 and end 2024-10-02. An exclusion sensitivity was completed separately; it does not modify this CSV.

## Frozen source and lineage

The immediate source is the `V2 P2 2024 Common Support` worksheet (rows 7–66) of `Polymarket_Full_Master_2006_2020_V2_Final_Results_Summary.xlsx`, with values verified against the authoritative `V2 P2 2024 Evaluation` and `V2 P2 2024 Bootstrap Inference` sheets. That large internal audit workbook is intentionally not committed to this repository.

The public CSV column names use plain **polling model** terminology rather than the development-version names in the internal audit workbook. Source mapping:

| Public CSV field | Frozen common-support field |
| --- | --- |
| `p_poll_dem` | `p_poll_dem_p2` |
| `p_market_dem` | `p_market_dem` |
| `p_hybrid_dem` | `p_hybrid_p2` |
| `poll_weighted_margin` | `v2_p2_weighted_poll_margin` |
| `y_dem_win` | `y_dem_win` |
| `source_data_anomaly_present` | same field |

Other market-data provenance is preserved via market observation timestamp and archived source-row identifiers.

**Market source:** the `data/2024-senate-polymarket-prices.json` archive at `jacksonjude/USA-Election-Map-Data`, commit `f0c6732787c21f5b084a5626f3c558a082239db1`, frozen market blob SHA `23c902a99fc4b92882226f7bd5b28aeaac37840e`. The underlying extraction used Polymarket CLOB prices-history with `interval=max`, `fidelity=720`, and the scheduled noon UTC 12-hour grid observation. The `market_source_row` in the CSV is the archived processed-market source-row locator, **not** a live Polymarket transaction ID.

**Outcome source:** [U.S. House Clerk, *Statistics of the Presidential and Congressional Election of November 5, 2024*](https://clerk.house.gov/member_info/electionInfo/2024/statistics2024.pdf). Page locators for each race are in `outcome_source_locator`.

## Reproduce the published statistics

From the repository root:

```bash
python -m pip install -r requirements.txt
python src/evaluate_2024.py
```

The script checks the frozen sample, computes Brier and log loss by horizon and pooled, applies 25% weight to each horizon for the primary aggregate, and runs a **50,000-replicate whole-race bootstrap** with seed **2026**, NumPy **PCG64**, and alphabetically sorted races. It uses simple 95% percentile intervals, no model refitting and no redrawing. It exits with an error if computed results deviate from the frozen workbook at the regression-test tolerance.

To save the machine-readable summary (the `outputs/tables` directory is gitignored for generated files):

```bash
python src/evaluate_2024.py --json outputs/tables/2024_reproduction.json
```

The 2024 results are **locked-spec retrospective evaluation**, not pristine prospective validation of the final polling specification. The finalized methodology's forward-looking test is 2026.

## 2022 development common-support data

[`2022_common_support.csv`](2022_common_support.csv) is a frozen, full-precision, **34-observation** PRIMARY development extract from `V2 P2 2022 Common Support` in the internal `Polymarket_Full_Master_2006_2020_V2_Final_Results_Summary.xlsx` workbook (source worksheet rows 7–44, `sample_status = PRIMARY_2022` only). The workbook is not committed.

- **Horizon counts:** 60d = 7, 30d = 8, 14d = 9, 7d = 10; **10 distinct Senate races**.
- Four **Georgia post-general runoff robustness** observations are present in the original 38-row common-support workbook, but are **deliberately excluded** from the development CSV and the hybrid fit. Their inclusion would change the frozen fitting sample.
- Public-facing `p_poll_dem` corresponds to internal `p_poll_dem_p2` (the final quality-weighted model). `p_market_dem` and `y_dem_win` are frozen inputs, not calculated by the fitting script. `p_poll_dem_v1` is retained only for provenance, not fitted or used in this script.
- `market_source_file` and `market_source_blob_sha` identify the archive's individual state data file; `market_source_row` locates the corresponding observation in the frozen processed-market workbook, **not an exchange trade ID**. `outcome_source_locator` identifies the certified election-return source.
- Archived 2022 market data: [`tanaerao/polymarket-midterms`](https://github.com/tanaerao/polymarket-midterms) at commit `7adf1aa694d988e892edd0f03fc23b046a38599a`. Original trade timestamps are timezone-naive; the frozen market extraction **treated them as UTC**, choosing the last price at or before the horizon's noon UTC cutoff. The source/session timezone could not be independently established, so this is a stated data limitation, not an implicit timezone verification.
- Election results: [FEC, *Federal Elections 2022*](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/federal-elections-2022/). Outcome coding is `y_dem_win = 1` for a Democratic victory and 0 otherwise.

### Reproduce the frozen global hybrid weight

From the repository root:

```bash
python -m pip install -r requirements.txt
python src/fit_hybrid_2022.py
python -m unittest discover -s tests -v
```

The script calculates the **unconstrained quadratic optimum** of the 34-observation equal-horizon Brier objective (each horizon receives 25%), then imposes `0 <= w <= 1` on the **single global weight**. It reports horizon-by-horizon, equal-horizon and pooled Brier and log-loss diagnostics, but **log loss is not an optimization objective**. All outputs are checked against frozen workbook values (tolerance `1e-12`). No re-estimation of pollster quality, historical calibration, polling or market probabilities takes place.

The original V1 project comparison is distinct from the later locked-spec retrospective extension; this 2022 development reproduction uses the **final polling model**. The finalized approach is intended to be tested prospectively in 2026; 2024 is retrospective, not pristine untouched validation.

## 2006–2020 historical polling calibration

[`2006_2020_polling_signals.csv`](2006_2020_polling_signals.csv) is a **full-precision, 531-row frozen signal-level extract** from the internal `Polymarket_Full_Master_2006_2020_V2_Final_Results_Summary.xlsx`. It contains one pre-election Senate race × horizon polling signal per row, its certified Democratic-minus-Republican election margin, fixed PRIMARY/runoff classification, source metadata, and original workbook row locators. **The large audit workbook is not committed.**

**Source worksheets:**

- `V2 P2 All Signals 2006-2020` (Excel rows 2–532): frozen final quality-weighted polling margins, poll counts, weighted totals, horizon/cutoff and signal-source pointers.
- `V2 P2 Historical Polling Errors` (rows 2–532): the exact 531-to-531 outcome merge, certified outcome margin, FEC provenance and PRIMARY versus procedural-runoff status.
- `V2 P2 Polling Error Parameters` (rows 8–11): frozen benchmark values for the regression tests; **not used to estimate** the parameters.

The source's `PRIMARY_V1_1` and `POST_GE_RUNOFF_ROBUSTNESS` strings are original internal audit status identifiers. They are carried through unchanged for source reconciliation, not separate public-facing forecasting models.

| Historical cycle | Signal count |
| --- | ---: |
| 2006 | 33 |
| 2008 | 69 |
| 2010 | 70 |
| 2012 | 79 |
| 2014 | 98 |
| 2016 | 69 |
| 2018 | 70 |
| 2020 | 43 |
| **Total** | **531** |

**Calibration sample:** 527 PRIMARY signals (60d: 93; 30d: 133; 14d: 150; 7d: 151). The four additional `2008-georgia-{60,30,14,7}d` signals are **post-general runoff robustness only** and do not contribute to any parameter estimate.

For horizon `h`, compute the historical error as:

```text
error(i,h) = certified_D_minus_R_margin(i) - frozen_poll_D_minus_R_margin(i,h)

mu_h = arithmetic_mean(PRIMARY errors at horizon h)
sigma_h = sample_standard_deviation(PRIMARY errors at horizon h, ddof=1)
```

No race or horizon receives any additional observation weight. The script also reports mean absolute error as an audit diagnostic. The four frozen calibration pairs are verified against the historical workbook to absolute tolerance `1e-12`.

**Signal origins:** the [Jack-Whitcomb Senate polling archive](https://github.com/Jack-Whitcomb/All-US-Senate-polls-2006-2024/blob/5aea8c5c4572ddc71f4491fa84478e70d88a5898/2006_to_2024_senate_polls.csv), pinned commit `5aea8c5c4572ddc71f4491fa84478e70d88a5898`. Source polling labels and historical aggregation were frozen in the original audit before joining election outcomes. **Certified outcome origins:** FEC *Federal Elections* for 2006, 2008, 2010, 2012, 2014, 2016, 2018 and 2020. Per-signal FEC source links appear in `outcome_source_url`; the vote-margin denominator is all valid votes cast, not a two-party denominator.

### Reproduce the historical calibration

```bash
python src/calibrate_polling_2006_2020.py
python src/calibrate_polling_2006_2020.py --csv outputs/tables/historical_calibration.csv
python -m unittest discover -s tests -v
```

This stage **reproduces the calibration from the 531 already-frozen historical polling signals**. It independently reconstructs the 527 PRIMARY historical errors, horizon-specific means, sample standard deviations, and MAEs. It also checks the source record counts and stored error arithmetic.

The standalone calibration script begins with the 531 frozen signal rows. The later poll-level weighting stage now reconstructs all 531 margins, and `generate_polling_forecasts.py` substitutes those independently rebuilt margins before estimating the same calibration. No new historical parameters or model variants are fitted.

## Vintage-safe pollster reliability and quality

This stage reconstructs the frozen **historical pollster-quality histories**, without touching polling aggregation, probabilities, or subsequent evaluation outcomes.

The two inputs are:

- [`historical_reliability_errors.csv`](historical_reliability_errors.csv): **1,005 individually eligible historical Senate poll errors**, across 2006–2022, with frozen conducting (`reliability_pollster`) identities, poll and certified Democratic-minus-Republican margins, signed and absolute errors, election cycle and original source/provenance fields. These come from the **`Reliability Error Inputs`** sheet stored as JSONL row chunks in the internal workbook’s `Archived Source Sheets` tab. The CSV retains `archived_excel_row` to locate every source record.
- [`historical_quality_reference.csv`](historical_quality_reference.csv): all **2,729 frozen pollster × forecast-vintage lookup keys** and full-precision reference statistics, from `Pollster Quality Weight Audit` (the frozen p=2 calculation sheet). This is used **only to identify the frozen lookup universe and to check** the independently recomputed values, not to obtain prior MAEs or multipliers used in reconstruction. The CSV retains `audit_excel_row`.

The analysis underlying the inputs is in the internal `Polymarket_Full_Master_2006_2020_V2_Final_Results_Summary.xlsx` workbook. That large audit workbook is deliberately not tracked in Git.

### Frozen selection and source scope

The **1,005 already-eligible error observations** are the vetted reliability-error universe, not all historical raw poll rows. Eligibility, joint-poll decomposition and canonical-to-conducting identity decisions were established in the frozen audit; no new poll selection or pollster-alias inference occurs in this stage. The public source does not yet independently reconstruct reliability eligibility from the entire raw polling archive; the poll-level input/weighting pipeline is planned separately.

Cycle counts in the reliability-error input: 2006: 100; 2008: 120; 2010: 106; 2012: 118; 2014: 143; 2016: 118; 2018: 105; 2020: 84; 2022: 111. Historical poll rows trace to the [pinned Senate archive](https://github.com/Jack-Whitcomb/All-US-Senate-polls-2006-2024/blob/5aea8c5c4572ddc71f4491fa84478e70d88a5898/2006_to_2024_senate_polls.csv) at commit `5aea8c5c4572ddc71f4491fa84478e70d88a5898`; certified result links are recorded by row.

### Reproduce

```bash
python src/reconstruct_pollster_quality.py
python src/reconstruct_pollster_quality.py --csv outputs/tables/pollster_quality.csv
python -m unittest discover -s tests -v
```

The reconstruction derives `absolute_error = |actual_margin - poll_margin|` from stored polling and election margins, validating the frozen error fields. For each forecast vintage `t` and resolved conducting pollster `j`, it uses **only poll-error records with `cycle < t`** to compute `n_prior_polls`, `raw_prior_MAE_j`, and the global mean absolute error of **all eligible prior polls**. No poll released or conducted in cycle `t` contributes to its own vintage.

```text
shrunk_MAE_j(t) = (n_j / (n_j + 18)) * raw_prior_MAE_j
                + (18 / (n_j + 18)) * prior_global_MAE(t)
q_j(t) = (prior_global_MAE(t) / shrunk_MAE_j(t)) ^ 2
```

The 2006 vintage has **no prior universe** (global MAE and shrunk MAE are blank; every q = 1). In later vintages, genuinely no-history pollsters retain blank raw MAE, use shrunk MAE equal to the contemporary global MAE and have **q = 1**. No clipping/clamping or post-2022 election outcomes are used.

- Forecast vintages: 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022 and 2024.
- Frozen lookup universe: **272 entries per vintage** through 2022, then **281** for 2024, total **2,729**.
- For 2022 forecasts, the history ends in **2020**: 894 prior eligible polls; global MAE `4.509642792245872`.
- For 2024 forecasts, history ends in **2022**: 1,005 prior eligible polls; global MAE `4.457949518496256`.
- Every frozen n, raw MAE, global MAE, shrunk MAE, q and vintage flag is independently checked against the authoritative reference at absolute tolerance **1e-12**. Largest observed numerical difference: about `3.55e-15`.

The produced `outputs/tables/pollster_quality.csv` is the **computed** vintage-safe quality table for later poll-level weighting. It is not a new fitted model or a replacement for the underlying archived identity audit. No 2024 election outcomes were used to determine 2024 quality multipliers.

## Poll-level weighting pipeline (frozen 2006–2024)

This stage reconstructs the final **quality-weighted polling signal** from frozen, eligible individual poll usages; it does not refit models, score elections, or change any eligibility rule.

### Inputs and traceability

- [`poll_usages_2006_2012.csv`](poll_usages_2006_2012.csv): **3,108** uses of polls in 2006–2012 Senate forecasts, exported from the original `Poll Usage Weights 2006-2020` audit sheet (original rows retained).
- [`poll_usages_2014_2020.csv`](poll_usages_2014_2020.csv): **2,902** uses in 2014–2020 from the same audit sheet. Together the historical inputs comprise **6,010 usages**.
- [`poll_usages_2022.csv`](poll_usages_2022.csv): **469** uses from the frozen `V1 2022 Row Weights` and the exact resolved identities from `V2 P2 2022 Row Weights`.
- [`poll_usages_2024.csv`](poll_usages_2024.csv): **867** uses from frozen `V1 2024 Row Weights` and `V2 P2 2024 Row Weights`.
- [`pollster_identity_2022_2024.csv`](pollster_identity_2022_2024.csv): documentary raw-label fielding crosswalk, limited to the **64** labels actually used in 2022 and **70** actually used in 2024. The earlier 2022 identity lookup has 67 listed labels, of which three are outside the frozen selected-usage universe; this export includes only actual usages.
- [`polling_signal_reference_2006_2024.csv`](polling_signal_reference_2006_2024.csv): **629** frozen race×horizon aggregation benchmarks; reference values are used for validation only, never as inputs to reconstructed weights or margins.
- Existing Step 2: [`historical_reliability_errors.csv`](historical_reliability_errors.csv), [`historical_quality_reference.csv`](historical_quality_reference.csv), and [`src/reconstruct_pollster_quality.py`](../../src/reconstruct_pollster_quality.py). Historical quality multipliers are *recomputed* from prior-election errors, not loaded from the stored row-weight outputs.

The single internal provenance workbook is `Polymarket_Full_Master_2006_2020_V2_Final_Results_Summary.xlsx` (40 worksheets). The source sheet names above refer to that file. Its large size is why it is excluded from Git; each exported usage preserves its original source file/row, source identifier, field dates, raw and original canonical pollster labels, reliability identity, poll margin and source Excel row. Full-precision frozen row weights and signal metrics appear only as **regression-test reference columns**; the algorithm cannot use them to calculate its outputs.

### Frozen row weight (no new weighting choices)

For a poll usage in a specific race×horizon `h`, let:

- `age = (cutoff - start date) - (end date - start date) / 2` in days. This preserves half-day median-field precision, using the *recorded* dates without any source repair.
- `w_recency = 2 ** (-age / (14 + 0.2*h))`.
- `effective_n = min(reported_sample_size, 5000)`, with missing `n` replaced by `600`.
- `w_sample = sqrt(effective_n / 600)`.
- `bin = floor(age / 14)`; group **within the race×horizon signal** by `(original_v1_canonical_pollster, bin)` and set `w_repeat = 1 / number_of_eligible_polls_in_this_bin`. **The later reliability identity must not be used for these bins.**
- `w_partisan = 1`, `w_v1_quality = 1`.
- `v1_poll_weight = w_recency * w_sample * w_repeat`.
- `v2_p2_poll_weight = v1_poll_weight * q`, where `q` is the exact frozen forecast-vintage multiplier reconstructed by Step 2. For documentary **CONFIRMED_NO_HISTORY** identities absent from its key universe, `q=1` only after confirming no prior eligible errors under that exact identity. No fuzzy or heuristic fielding-identity matching is used.

The output polling margin is `sum(w * (dem - rep)) / sum(w)`; the maximum single-poll weight share is `max(w) / sum(w)`. All computations are independently checked against the frozen row weights and signal benchmark values.

### Known reversed-date source rows

The original frozen universe includes a handful of **internally reversed fielding-date records**. The script retains the recorded values rather than silently correcting or dropping them. There are **10 affected poll usages**, covering four distinct source records:

| Source | Original source row | Affected signals |
| --- | ---: | --- |
| `2016_senate_polls.csv` | 31 | Utah 60d, 14d, 7d |
| `2020_senate_polls.csv` | 117 | Maine 30d, 14d, 7d |
| `2022_senate_polls.csv` | 181 | Iowa 14d, 7d |
| `2024_senate_polls.csv` | 5 | Arizona 14d, 7d |

The two 2024 Arizona usages retain their **previously identified and sensitivity-tested** `source_data_anomaly=True` flag. The earlier eight usages are additionally reported by `source_date_reversal_detected=True`, without retroactively changing the original anomaly classifications. The script rejects any new, unaccounted-for reversed-date record. No anomaly-exclusion sensitivity is run here.

### Reproduction and scope

Run from the repository root:

```bash
python src/reconstruct_poll_weights.py
python src/reconstruct_poll_weights.py \
  --rows-csv outputs/tables/rebuilt_poll_weights.csv \
  --signals-csv outputs/tables/rebuilt_polling_signals.csv
python -m unittest discover -s tests -v
```

Full-source outputs are not committed to `outputs/` and can be regenerated locally. Run time is typically under a few seconds. The reconstruction reproduces **7,346 poll usages** and **629 polling signals**: 531 historical, 38 development (2022), and 60 retrospective evaluation (2024). Maximum absolute difference from a frozen aggregate weighted margin is approximately `1.42e-14`; every row-level stored V1 and quality-weighted p=2 weight also reconciles to `1e-10`.

This stage **does not reconstruct polling-archive eligibility filtering or independently redo the documentary pollster-identity investigations**. Those are deliberately held fixed to preserve the retrospective experiment. The downstream forecasting stage uses these regenerated margins to recompute the historical calibration and the 2022/2024 polling probabilities. The 2024 comparison is retrospective, and 2026 remains the prospective test.

## 2022 and 2024 polling forecasts from poll rows

[`generate_polling_forecasts.py`](../../src/generate_polling_forecasts.py) links the first three reconstruction stages into the final polling forecasts. It does not load a stored polling margin or probability as a model input.

1. Rebuild all 7,346 poll-usage weights and 629 race×horizon margins.
2. Join the 531 reconstructed 2006–2020 margins to the already-frozen certified outcomes and PRIMARY/runoff classifications.
3. Re-estimate the four horizon-specific error means and sample standard deviations from the 527 PRIMARY observations.
4. For each reconstructed 2022 and 2024 margin, calculate:

```text
z(i,h) = (polling_margin(i,h) + mu_h) / sigma_h
p_poll_dem(i,h) = Phi(z(i,h))
p_poll_rep(i,h) = 1 - p_poll_dem(i,h)
```

The output contains **98 polling forecasts**: 38 for 2022 and 60 for 2024. The four `2022-georgia-{60,30,14,7}d` rows are generated and labeled `POST_GENERAL_RUNOFF_ROBUSTNESS`, but are not allowed into the 34-row PRIMARY development fit. The 2024 Arizona anomaly flags are propagated from the poll-level records without repairing or excluding the frozen source rows.

After generation, the script regression-checks the 34 PRIMARY 2022 probabilities against `2022_common_support.csv` and all 60 2024 probabilities and margins against `2024_common_support.csv`. The four Georgia robustness forecasts have no committed common-support reference because the frozen PRIMARY development extract excludes them. Frozen reference columns and common-support outputs are used only after generation for validation. Neither market probabilities nor 2022/2024 election outcomes enter the polling forecast calculation.

```bash
python src/generate_polling_forecasts.py
python src/generate_polling_forecasts.py \
  --csv outputs/tables/rebuilt_polling_forecasts.csv \
  --json outputs/tables/rebuilt_polling_forecasts_audit.json
python -m unittest discover -s tests -v
```

Generated tables are gitignored and can be recreated on demand. This stage leaves the 2022 hybrid fitting rule and the 2024 evaluation unchanged.

## Prediction-market source reconstruction

[`reconstruct_market_probabilities.py`](../../src/reconstruct_market_probabilities.py) rebuilds the market probabilities that feed the 2022 development fit and 2024 retrospective evaluation. The calculation starts from upstream raw bytes, not from the committed `p_market_dem` columns. Those columns are read only after reconstruction as regression-test targets.

The machine-readable source manifest is [`data/raw/market_sources.json`](../raw/market_sources.json). It pins repository commits, file paths and Git blob SHAs. Raw upstream files are downloaded to a gitignored cache or supplied from local pinned checkouts; they are not redistributed in this repository because neither pinned source tree contains a license file.

### 2022 trade-level rule

The script verifies and parses ten state-specific CSVs containing **6,779 trades** in total. For each of the 34 PRIMARY targets:

1. construct 12:00:00 UTC on the stored cutoff date;
2. interpret the source's timezone-naive `Timestamp` as UTC under the frozen convention;
3. select the latest trade at or before the target;
4. if several rows share that timestamp, retain the first physical source row;
5. set `p_market_dem = price` for a Democratic contract and `1 - price` for a Republican contract.

The original scraper/session timezone remains unresolved. The convention is preserved and disclosed rather than relabeled as verified UTC. Georgia's four post-general-runoff observations are not in the committed PRIMARY common-support market sample and are not reconstructed by this stage.

### 2024 archived CLOB rule

The script verifies the single 2024 JSON blob, validates **13,966 observations across 33 states**, and selects the price-history point nearest each scheduled noon UTC target. A point more than 60 seconds from the target is rejected instead of silently substituting an adjacent 12-hour observation. All 60 frozen selections are 2 or 3 seconds after their target. No interpolation or smoothing is performed.

### Run and verify

```bash
python src/reconstruct_market_probabilities.py
python src/reconstruct_market_probabilities.py \
  --csv outputs/tables/rebuilt_market_probabilities.csv \
  --json outputs/tables/rebuilt_market_probabilities_audit.json
python -m unittest discover -s tests -v
```

The reconstruction checks **94 observations**. The maximum absolute difference from the committed market probabilities is about `5.55e-17` for 2022 and exactly `0` for 2024. The 2024 observed timestamps also match exactly.
