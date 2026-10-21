# Source code

The final reproducible pipeline will be organized into small modules for:

- polling ingestion and normalization;
- vintage-safe pollster reliability;
- poll weighting and aggregation;
- historical polling-error calibration;
- polling probability generation;
- prediction-market processing (`reconstruct_market_probabilities.py`);
- 2022 hybrid fitting;
- 2024 evaluation and clustered bootstrap inference;
- 2026 prospective forecast generation.

The development analysis was completed in an extensive audit workbook. Code added here should reproduce the final specification rather than every intermediate experimental version.

## Prediction-market reconstruction

`reconstruct_market_probabilities.py` retrieves or reads local copies of the exact upstream 2022 trade CSVs and 2024 CLOB-history archive listed in `data/raw/market_sources.json`. It verifies Git blob SHAs before parsing, applies the frozen timestamp and contract-side rules, and regression-checks all 94 PRIMARY market probabilities.

```bash
python src/reconstruct_market_probabilities.py
python src/reconstruct_market_probabilities.py \
  --csv outputs/tables/rebuilt_market_probabilities.csv
```

Raw upstream files remain outside version control. See `data/raw/README.md` for source-license status, cache behavior and offline local-checkout usage.
