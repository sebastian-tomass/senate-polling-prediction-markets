"""Reproduce the frozen 2022 Senate polling/market convex-hybrid development fit.

Run from the repository root: python src/fit_hybrid_2022.py

Uses only the 34 frozen 2022 PRIMARY common-support observations. It does not
construct forecasts, alter pollster quality, or use 2024 data.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

HORIZONS = (60, 30, 14, 7)
HORIZON_COUNTS = (7, 8, 9, 10)
DEFAULT_DATA = Path(__file__).resolve().parents[1] / 'data/processed/2022_common_support.csv'

# Frozen audit-workbook regression targets, never used to choose or fit w.
FROZEN = {
    'weighted_cross_term': 0.004060284941899114,
    'weighted_squared_delta': 0.012048154629401706,
    'w_unconstrained': -0.3370047170535644,
    'w_constrained': 0.0,
    'poll_equal_brier': 0.12919196173939043,
    'poll_equal_log_loss': 0.42433553370935817,
    'market_equal_brier': 0.10902323722619048,
    'market_equal_log_loss': 0.36582198107907393,
    'poll_pooled_brier': 0.12607894585103324,
    'poll_pooled_log_loss': 0.41617613741037957,
    'market_pooled_brier': 0.10871179323529413,
    'market_pooled_log_loss': 0.362662697263648,
}


def load_data(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        required = {'polling_signal_id', 'state', 'horizon_days', 'cutoff_date',
                    'sample_status', 'p_poll_dem', 'p_market_dem', 'y_dem_win'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'Missing required columns: {required - set(reader.fieldnames or [])}')
        rows = list(reader)
    if len(rows) != 34 or len({r['polling_signal_id'] for r in rows}) != 34:
        raise ValueError('Expected exactly 34 unique PRIMARY race-horizon observations')
    if len({r['state'].lower() for r in rows}) != 10:
        raise ValueError('Expected 10 distinct PRIMARY Senate races')
    if tuple(sum(int(r['horizon_days']) == h for r in rows) for h in HORIZONS) != HORIZON_COUNTS:
        raise ValueError('Expected horizon counts of 7/8/9/10')
    for r in rows:
        if r['sample_status'] != 'PRIMARY_2022' or r['state'].strip().lower() == 'georgia':
            raise ValueError('Georgia runoff and non-PRIMARY observations cannot enter development')
        if r['polling_signal_id'] != f"2022-{r['state'].lower().replace(' ', '-')}-{int(r['horizon_days'])}d":
            raise ValueError(f"Inconsistent race-horizon identifier: {r['polling_signal_id']}")
        if r['y_dem_win'] not in ('0', '1'):
            raise ValueError(f"Invalid certified binary outcome: {r['polling_signal_id']}")
        for column in ('p_poll_dem', 'p_market_dem'):
            p = float(r[column])
            if not np.isfinite(p) or not (0.0 < p < 1.0):
                raise ValueError(f"Invalid {column} in {r['polling_signal_id']}")
    return rows


def _score(probabilities: np.ndarray, outcomes: np.ndarray, horizons: np.ndarray) -> dict:
    brier = (probabilities - outcomes) ** 2
    log_loss = -(outcomes * np.log(probabilities) + (1.0 - outcomes) * np.log1p(-probabilities))
    correct = ((probabilities >= 0.5) == (outcomes == 1.0))
    by_horizon = {
        str(h): {'n': int(np.count_nonzero(horizons == h)),
                 'brier': float(brier[horizons == h].mean()),
                 'log_loss': float(log_loss[horizons == h].mean()),
                 'accuracy': float(correct[horizons == h].mean())}
        for h in HORIZONS
    }
    equal = {key: float(np.mean([by_horizon[str(h)][key] for h in HORIZONS]))
             for key in ('brier', 'log_loss')}
    return {'by_horizon': by_horizon, 'equal_horizon': equal,
            'pooled': {'brier': float(brier.mean()), 'log_loss': float(log_loss.mean()),
                       'accuracy': float(correct.mean())}}


def fit_hybrid(rows: list[dict[str, str]]) -> dict:
    h = np.array([int(r['horizon_days']) for r in rows], dtype=int)
    poll = np.array([float(r['p_poll_dem']) for r in rows], dtype=float)
    market = np.array([float(r['p_market_dem']) for r in rows], dtype=float)
    y = np.array([int(r['y_dem_win']) for r in rows], dtype=float)

    d = poll - market
    # Equal-horizon objective: each of 60/30/14/7 days gets exactly 1/4.
    cross = float(np.mean([(d[h == t] * (market[h == t] - y[h == t])).mean()
                           for t in HORIZONS]))
    curvature = float(np.mean([(d[h == t] ** 2).mean() for t in HORIZONS]))
    if curvature <= 0:
        raise ValueError('Degenerate fit: polling and market inputs have zero weighted difference')
    w_unconstrained = -cross / curvature
    w_frozen = float(np.clip(w_unconstrained, 0.0, 1.0))
    hybrid = w_frozen * poll + (1.0 - w_frozen) * market
    if np.any(hybrid <= 0.0) or np.any(hybrid >= 1.0):
        raise ValueError('Hybrid probabilities must be strictly between zero and one')
    return {'sample': {'n_primary': 34, 'n_georgia_in_fit': 0, 'n_races': 10,
                       'horizon_counts': dict(zip(map(str, HORIZONS), HORIZON_COUNTS)),
                       'horizon_objective_share': {str(t): 0.25 for t in HORIZONS}},
            'fit': {'objective': 'equal_horizon_brier',
                    'weighted_cross_term': cross, 'weighted_squared_delta': curvature,
                    'w_unconstrained': float(w_unconstrained),
                    'w_constrained': w_frozen},
            'scores': {'polling': _score(poll, y, h),
                       'market': _score(market, y, h),
                       'hybrid': _score(hybrid, y, h)}}


def verify_frozen(report: dict, atol: float = 1e-12) -> None:
    values = dict(report['fit'])
    for prefix, model in (('poll', 'polling'), ('market', 'market')):
        for level in ('equal_horizon', 'pooled'):
            for metric in ('brier', 'log_loss'):
                values[f'{prefix}_{"equal" if level == "equal_horizon" else "pooled"}_{metric}'] = (
                    report['scores'][model][level][metric])
    mismatches = {key: {'expected': expected, 'actual': values[key]}
                  for key, expected in FROZEN.items()
                  if abs(values[key] - expected) > atol}
    if mismatches:
        raise AssertionError(f'Frozen development audit mismatch: {mismatches}')
    if report['scores']['hybrid'] != report['scores']['market']:
        raise AssertionError('At frozen w=0, hybrid must exactly equal market on every metric')
    if report['fit']['w_constrained'] != 0.0:
        raise AssertionError('Frozen constrained polling weight changed')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--json', type=Path, help='Optionally write the full report to JSON')
    args = parser.parse_args()
    report = fit_hybrid(load_data(args.data))
    verify_frozen(report)
    report['frozen_audit_verified'] = True
    payload = json.dumps(report, indent=2) + '\n'
    print(payload, end='')
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding='utf-8')


if __name__ == '__main__':
    main()
