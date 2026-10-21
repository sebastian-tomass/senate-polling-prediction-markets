# Data sources and provenance

This file records the source families used by the project. Exact prediction-market source paths and checksums are machine-readable in [`data/raw/market_sources.json`](../data/raw/market_sources.json).

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

The 2022 Senate market series comes from the public [`tanaerao/polymarket-midterms`](https://github.com/tanaerao/polymarket-midterms/tree/7adf1aa694d988e892edd0f03fc23b046a38599a) trade archive at commit `7adf1aa694d988e892edd0f03fc23b046a38599a`. Ten state-specific Senate CSVs supply the 34 PRIMARY development observations. The upstream README says the records were scraped from Jeff Rossiter's PolymarketWhales. The manifest records each file's Git blob SHA.

The CSV `Timestamp` strings are timezone-naive. The frozen convention treats them as UTC because the original scraper/session timezone cannot be independently established. At each target horizon, the project selects the last available trade at or before 12:00:00 UTC, using the first physical source row when several trades share the selected timestamp. A selected Democratic contract uses `price`; a selected Republican contract uses `1 - price`.

## Prediction markets — 2024

The 2024 Senate market series comes from `data/2024-senate-polymarket-prices.json` in [`jacksonjude/USA-Election-Map-Data`](https://github.com/jacksonjude/USA-Election-Map-Data/tree/f0c6732787c21f5b084a5626f3c558a082239db1), commit `f0c6732787c21f5b084a5626f3c558a082239db1`, Git blob SHA `23c902a99fc4b92882226f7bd5b28aeaac37840e`.

The JSON is an archived Polymarket CLOB `prices-history` response produced with `interval=max` and `fidelity=720` minutes. The pinned source tree contains the response but no extraction script or market token-ID registry. The project therefore reproduces normalization from the immutable archive rather than requerying a mutable live endpoint. It selects the observation nearest each scheduled 12:00:00 UTC target and fails if none is within 60 seconds. Every frozen common-support selection occurs 2 or 3 seconds after the scheduled target. Prices in this archive are already Democratic contract probabilities.

## Reproducibility plan

The public repository separates:

- source metadata and retrieval instructions;
- processed modeling tables;
- transformation scripts;
- output tables and figures.

Large audit workbooks are intentionally excluded from version control by default. The market reconstruction can use verified downloads or exact local upstream checkouts and does not require the development workbook.

The two pinned prediction-market source trees contain no `LICENSE` or `COPYING` file. The project therefore does not vendor their raw data. The manifest and transformation code are committed; downloads go to a gitignored cache. This is a conservative redistribution policy, not a legal conclusion about the underlying factual data.

## Source-integrity notes

The audit process preserves known source anomalies rather than silently correcting uncertain records.

One malformed 2024 Arizona polling record has reversed start/end dates. The primary analysis retains it for frozen-universe comparability, while a separate exclusion sensitivity confirms that it does not materially change the final comparison.
