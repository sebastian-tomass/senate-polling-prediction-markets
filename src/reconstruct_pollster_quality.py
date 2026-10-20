"""Reproduce vintage-safe Senate pollster reliability from frozen eligible poll errors.

Run from the repository root:
    python src/reconstruct_pollster_quality.py
    python src/reconstruct_pollster_quality.py --csv outputs/tables/pollster_quality.csv

Inputs are frozen, already-eligible poll-error observations and the frozen audit
universe of forecast-cycle / conducting-pollster identities. Neither input is
constructed with later-cycle information for an earlier forecast vintage.
This is a reconstruction, not a new fitting or pollster-alias-matching step.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERROR_INPUT = ROOT / 'data' / 'processed' / 'historical_reliability_errors.csv'
REFERENCE_INPUT = ROOT / 'data' / 'processed' / 'historical_quality_reference.csv'
K = 18
P = 2
VINTAGES = (2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024)
EXPECTED_ERROR_CYCLES = {2006: 100, 2008: 120, 2010: 106, 2012: 118,
                         2014: 143, 2016: 118, 2018: 105, 2020: 84, 2022: 111}
EXPECTED_AUDIT_VINTAGES = {**{year: 272 for year in VINTAGES[:-1]}, 2024: 281}
CHECK_TOL = 1e-12


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as file:
        return list(csv.DictReader(file))


def number(value: str) -> float | None:
    if value is None or value == '':
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite numeric input')
    return result


def load_errors(path: Path = ERROR_INPUT) -> list[dict]:
    source = read_csv(path)
    if len(source) != 1005:
        raise ValueError(f'Expected 1005 reliability error records, found {len(source)}')
    errors = []
    unique_rows = set()
    for row in source:
        original_row = int(row['archived_excel_row'])
        if original_row in unique_rows:
            raise ValueError(f'Duplicate archive row: {original_row}')
        unique_rows.add(original_row)
        cycle = int(row['cycle'])
        if cycle not in EXPECTED_ERROR_CYCLES:
            raise ValueError(f'Unexpected reliability-error cycle {cycle}')
        identity = row['reliability_pollster']
        if not identity:
            raise ValueError(f'Missing reliability identity at archive row {original_row}')
        margin, actual = number(row['poll_margin']), number(row['actual_margin'])
        signed, absolute = actual - margin, abs(actual - margin)
        if abs(signed - number(row['signed_error'])) > CHECK_TOL or abs(absolute - number(row['absolute_error'])) > CHECK_TOL:
            raise ValueError(f'Historical poll error inconsistency at archive row {original_row}')
        errors.append({'cycle': cycle, 'identity': identity, 'absolute_error': absolute,
                       'archived_excel_row': original_row})
    counts = dict(Counter(e['cycle'] for e in errors))
    if counts != EXPECTED_ERROR_CYCLES:
        raise ValueError(f'Historical eligible-error cycle counts changed: {counts}')
    return errors


def load_reference(path: Path = REFERENCE_INPUT) -> list[dict[str, str]]:
    records = read_csv(path)
    if len(records) != 2729:
        raise ValueError(f'Expected 2729 pollster-vintage keys, found {len(records)}')
    keys = [(int(float(r['forecast_cycle'])), r['reliability_pollster']) for r in records]
    if len(set(keys)) != len(keys) or any(not name for _, name in keys):
        raise ValueError('Duplicate or missing reliability lookup keys')
    counts = dict(Counter(vintage for vintage, _ in keys))
    if counts != EXPECTED_AUDIT_VINTAGES:
        raise ValueError(f'Frozen lookup universe changed: {counts}')
    return records


def reconstruct(errors: list[dict], reference: list[dict[str, str]]) -> list[dict]:
    """Use only cycle < forecast_cycle eligible errors for each vintage."""
    by_cycle = defaultdict(list)
    for error in errors:
        by_cycle[error['cycle']].append(error)
    out = []
    for vintage in VINTAGES:
        history = [error for cycle in sorted(by_cycle) if cycle < vintage
                   for error in by_cycle[cycle]]
        prior_global_n = len(history)
        prior_global_mae = (math.fsum(e['absolute_error'] for e in history) / prior_global_n
                            if prior_global_n else None)
        by_pollster = defaultdict(list)
        for e in history:
            by_pollster[e['identity']].append(e['absolute_error'])
        through = str(max((c for c in by_cycle if c < vintage), default='NONE'))
        for r in reference:
            if int(float(r['forecast_cycle'])) != vintage:
                continue
            identity = r['reliability_pollster']
            errors_for_p = by_pollster.get(identity, [])
            n = len(errors_for_p)
            raw = math.fsum(errors_for_p) / n if n else None
            # 2006 has no prior errors. For other no-history identities, use the
            # contemporaneous global prior but keep raw_prior_MAE genuinely empty.
            shrunk = ((n / (n + K)) * raw + (K / (n + K)) * prior_global_mae
                      if n else prior_global_mae)
            q = (prior_global_mae / shrunk)**P if n else 1.0
            if not math.isfinite(q) or q <= 0:
                raise ValueError(f'Invalid quality factor for {vintage} / {identity}')
            out.append({
                'forecast_cycle': vintage, 'reliability_pollster': identity,
                'n_prior_polls': n, 'raw_prior_MAE': raw,
                'prior_global_n': prior_global_n, 'prior_global_MAE': prior_global_mae,
                'shrunk_MAE': shrunk, 'quality_multiplier_p2': q,
                'reliability_data_through_cycle': through,
                'no_history_flag': 'YES' if not n else 'NO',
                'source_audit_excel_row': int(r['audit_excel_row']),
            })
    return out


def verify_frozen(reconstructed: list[dict], reference: list[dict[str, str]], *, tol=CHECK_TOL) -> dict:
    targets = {(int(float(r['forecast_cycle'])), r['reliability_pollster']): r for r in reference}
    if len(reconstructed) != len(targets):
        raise AssertionError('Reconstruction does not cover the frozen audit universe')
    numeric = ('n_prior_polls', 'raw_prior_MAE', 'prior_global_MAE', 'shrunk_MAE', 'quality_multiplier_p2')
    errors = []
    max_abs = 0.0
    for row in reconstructed:
        k = row['forecast_cycle'], row['reliability_pollster']
        target = targets[k]
        for field in numeric:
            actual, frozen = row[field], number(target[field])
            if actual is None or frozen is None:
                if actual is not None or frozen is not None:
                    errors.append((k, field, actual, frozen))
                continue
            delta = abs(actual - frozen)
            max_abs = max(max_abs, delta)
            if delta > tol:
                errors.append((k, field, actual, frozen))
        target_vintage = (str(int(float(target['reliability_data_through_cycle'])))
                          if target['reliability_data_through_cycle'] != 'NONE' else 'NONE')
        if row['reliability_data_through_cycle'] != target_vintage:
            errors.append((k, 'reliability_data_through_cycle',
                           row['reliability_data_through_cycle'], target_vintage))
        if row['no_history_flag'] != target['no_history_flag']:
            errors.append((k, 'no_history_flag', row['no_history_flag'], target['no_history_flag']))
        if row['n_prior_polls'] == 0 and row['quality_multiplier_p2'] != 1.0:
            errors.append((k, 'no-history neutrality'))
        if row['reliability_data_through_cycle'] != 'NONE' and int(row['reliability_data_through_cycle']) >= row['forecast_cycle']:
            errors.append((k, 'future history leak'))
    if errors:
        raise AssertionError(f'{len(errors)} differences from frozen audit; first ten: {errors[:10]}')
    return {'pollster_vintage_records': len(reconstructed), 'max_numeric_abs_difference': max_abs,
            'discrepant_records': 0,
            'reference_checks': len(reconstructed) * len(numeric)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, help='Optional destination for calculated vintage quality table')
    parser.add_argument('--json', type=Path, help='Optional destination for summary JSON')
    args = parser.parse_args()
    errors = load_errors()
    reference = load_reference()
    result = reconstruct(errors, reference)
    audit = verify_frozen(result, reference)
    summary = {
        'eligible_reliability_error_records': len(errors),
        'eligible_error_counts_by_cycle': EXPECTED_ERROR_CYCLES,
        'forecast_pollster_counts_by_vintage': EXPECTED_AUDIT_VINTAGES,
        'shrinkage_K': K, 'quality_power_p': P, 'quality_clamping': False,
        'vintage_snapshots': {
            str(vintage): {
                'prior_global_n': next(r['prior_global_n'] for r in result if r['forecast_cycle'] == vintage),
                'prior_global_MAE': next(r['prior_global_MAE'] for r in result if r['forecast_cycle'] == vintage),
                'matched_history_count': sum(r['n_prior_polls'] > 0 for r in result if r['forecast_cycle'] == vintage),
                'no_history_count': sum(r['n_prior_polls'] == 0 for r in result if r['forecast_cycle'] == vintage),
            } for vintage in VINTAGES
        },
        'frozen_audit': audit,
    }
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open('w', newline='', encoding='utf-8') as f:
            fields = list(result[0])
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result)
    serialized = json.dumps(summary, indent=2) + '\n'
    print(serialized, end='')
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(serialized, encoding='utf-8')


if __name__ == '__main__':
    main()
