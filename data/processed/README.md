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
