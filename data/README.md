# Data

This directory contains the compact datasets and source manifests needed to reproduce the final analysis.

Planned layout:

```text
data/
├── raw/          # retrieval manifests; source extracts only where redistribution permits
└── processed/    # analysis-ready polling, market, calibration, and common-support tables
```

## Principles

- Preserve source provenance and stable identifiers.
- Keep raw and processed data separate.
- Do not commit credentials, private data, or temporary downloads.
- Prefer compact CSV/Parquet inputs over the large development workbook.
- Document any source that cannot legally or practically be redistributed and provide retrieval instructions instead.

The large Excel audit workbook used during model development is intentionally excluded from version control by `.gitignore`.

The raw 2022 trade files and 2024 CLOB-history archive are not committed because their pinned upstream trees do not contain license files. [`raw/market_sources.json`](raw/market_sources.json) records exact commits, paths and Git blob SHAs; [`raw/README.md`](raw/README.md) explains verified retrieval.
