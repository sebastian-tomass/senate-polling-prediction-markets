# Raw market-source retrieval

This directory contains source metadata only. It does not contain copies of the upstream prediction-market archives.

[`market_sources.json`](market_sources.json) pins every source by repository commit, file path and Git blob SHA. The reconstruction script retrieves those exact bytes into the gitignored `.cache/market_sources/` directory or accepts local checkouts through command-line overrides.

## Redistribution decision

Neither pinned upstream tree contained a `LICENSE` or `COPYING` file when this stage was prepared. A public repository is not, by itself, an affirmative redistribution license. The project therefore does not vendor the raw trade CSVs or CLOB-history JSON. This is a conservative repository policy, not a legal conclusion about the underlying factual data.

If an upstream license is later added, review the license at the exact pinned commit before changing the manifest policy or copying source files into this repository.

## Pinned sources

- **2022 trade archive:** [`tanaerao/polymarket-midterms`](https://github.com/tanaerao/polymarket-midterms/tree/7adf1aa694d988e892edd0f03fc23b046a38599a), commit `7adf1aa694d988e892edd0f03fc23b046a38599a`. Ten Senate-market CSVs feed the 34 PRIMARY development observations. The upstream README says the records were scraped from Jeff Rossiter's PolymarketWhales rather than exported directly by this project.
- **2024 CLOB archive:** [`jacksonjude/USA-Election-Map-Data`](https://github.com/jacksonjude/USA-Election-Map-Data/tree/f0c6732787c21f5b084a5626f3c558a082239db1), commit `f0c6732787c21f5b084a5626f3c558a082239db1`, file `data/2024-senate-polymarket-prices.json`. The pinned tree contains data files but no extraction script or token-ID registry, so this pipeline reproduces normalization from the immutable archived response rather than requerying a mutable live endpoint.

Run the normal online retrieval:

```bash
python src/reconstruct_market_probabilities.py
```

Or use exact local checkouts without network access:

```bash
python src/reconstruct_market_probabilities.py \
  --offline \
  --source-2022-root /path/to/polymarket-midterms \
  --source-2024-json /path/to/2024-senate-polymarket-prices.json
```

Every path is checked against its manifest Git blob SHA before parsing. A mismatched local file or cache entry fails closed.
