# Data

This directory will contain the compact datasets needed to reproduce the final analysis.

Planned layout:

```text
data/
├── raw/          # source extracts or retrieval manifests where redistribution permits
└── processed/    # analysis-ready polling, market, calibration, and common-support tables
```

## Principles

- Preserve source provenance and stable identifiers.
- Keep raw and processed data separate.
- Do not commit credentials, private data, or temporary downloads.
- Prefer compact CSV/Parquet inputs over the large development workbook.
- Document any source that cannot legally or practically be redistributed and provide retrieval instructions instead.

The large Excel audit workbook used during model development is intentionally excluded from version control by `.gitignore`.
