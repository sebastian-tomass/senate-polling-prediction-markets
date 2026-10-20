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

It **does not yet regenerate all 531 weighted polling margins from their individual historical poll rows**. That upstream audit replacement is intentionally handled in the later vintage-safe pollster-quality and poll-level weighting implementation stages. No new historical parameters or model variants are fitted here.

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
