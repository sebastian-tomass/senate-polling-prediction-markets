# Data sources and provenance

This file records the source families used by the project. Exact source URLs, archive snapshots, commit hashes, and extraction scripts will be added alongside the reproducible data pipeline.

## Historical Senate polling

Historical polling is drawn from a public RealClearPolitics-derived Senate polling archive covering the 2006–2020 calibration period.

The project preserves raw source labels and maintains explicit mappings for:

- canonical pollster identity used by the original polling construction;
- reliability pollster identity used by the vintage-safe quality model;
- joint poll / sponsor / publisher decomposition where needed.

## Election outcomes

Certified federal election results are used to construct realized Democratic-minus-Republican Senate margins.

The margin denominator is all valid votes cast in the Senate contest, rather than a two-party-normalized denominator.

Post-general runoff cases are kept separate from the primary calibration/evaluation where the regular general election does not itself determine the winner.

## Prediction markets — 2022

The 2022 Senate market series comes from a trade-level Polymarket archive.

At each target horizon, the project uses the last available trade at or before the frozen cutoff and converts contract-side prices into Democratic win probability.

## Prediction markets — 2024

The 2024 Senate market series comes from archived Polymarket CLOB historical-price data sampled at 12-hour fidelity.

The project uses the last frozen observation on each target date.

## Reproducibility plan

The public repository will separate:

- source metadata and retrieval instructions;
- processed modeling tables;
- transformation scripts;
- output tables and figures.

Large audit workbooks are intentionally excluded from version control by default. The goal is for the public repository to reproduce the final analysis from compact, documented inputs rather than require the development workbook itself.

## Source-integrity notes

The audit process preserves known source anomalies rather than silently correcting uncertain records.

One malformed 2024 Arizona polling record has reversed start/end dates. The primary analysis retains it for frozen-universe comparability, while a separate exclusion sensitivity confirms that it does not materially change the final comparison.
