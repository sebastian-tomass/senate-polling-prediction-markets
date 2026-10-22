# Source code

The frozen retrospective pipeline is organized into small, independently tested modules for:

- polling ingestion and normalization;
- vintage-safe pollster reliability;
- poll weighting and aggregation;
- historical polling-error calibration;
- polling probability generation;
- prediction-market processing (`reconstruct_market_probabilities.py`);
- 2022 hybrid fitting;
- 2024 evaluation and clustered bootstrap inference;
- end-to-end checks (`run_pipeline.py`);
- final tables and figures (`build_presentation.py`).

The development analysis was completed in an extensive audit workbook. Code added here should reproduce the final specification rather than every intermediate experimental version.

## Complete pipeline

`run_pipeline.py` is the single entry point for the completed retrospective reproduction:

```bash
python src/run_pipeline.py
```

It calls the preceding reconstruction modules in process, assembles the actual 34-row 2022 and 60-row 2024 analysis joins from regenerated polling probabilities, repeats the hybrid fit and fixed bootstrap, and creates the final tables and figures. All frozen checks run before the audit file is written.

The offline default uses the committed market probabilities that the market module already verifies independently. Use `--rebuild-markets` to reacquire and normalize the checksum-pinned upstream market files within the same run.

The future 2026 prospective forecast generator is deliberately outside this completed retrospective pipeline; its specification must be frozen before election outcomes are observed.

## Prediction-market reconstruction

`reconstruct_market_probabilities.py` retrieves or reads local copies of the exact upstream 2022 trade CSVs and 2024 CLOB-history archive listed in `data/raw/market_sources.json`. It verifies Git blob SHAs before parsing, applies the frozen timestamp and contract-side rules, and regression-checks all 94 PRIMARY market probabilities.

```bash
python src/reconstruct_market_probabilities.py
python src/reconstruct_market_probabilities.py \
  --csv outputs/tables/rebuilt_market_probabilities.csv
```

Raw upstream files remain outside version control. See `data/raw/README.md` for source-license status, cache behavior and offline local-checkout usage.
