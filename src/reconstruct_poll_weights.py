"""Reproduce frozen Senate polling row weights and race×horizon aggregates.

Run from repository root:
    python src/reconstruct_poll_weights.py
    python src/reconstruct_poll_weights.py --rows-csv outputs/tables/rebuilt_poll_weights.csv --signals-csv outputs/tables/rebuilt_polling_signals.csv

Frozen poll-usage universes, original V1 pollster identities, and documentary
reliability crosswalks are inputs, NOT reconstructed through heuristic matching.
The q multipliers are computed by Step 2's vintage-safe quality module.
No outcomes, polling calibration, market prices or hybrid fitting are used.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from reconstruct_pollster_quality import (load_errors, load_reference,
                                          reconstruct, verify_frozen)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'processed'
HORIZONS = (60, 30, 14, 7)
EXPECTED_ROWS = {2006: 517, 2008: 739, 2010: 896, 2012: 956,
                 2014: 1037, 2016: 804, 2018: 497, 2020: 564,
                 2022: 469, 2024: 867}
# 2024 frozen PRIMARY deliberately retains a source poll with reversed dates;
# no other row may have start > end or carry the source-data anomaly flag.
ANOMALOUS_SIGNALS = {'2024-arizona-14d', '2024-arizona-7d'}
ANOMALOUS_SOURCE_ROW = 5
FROZEN_OTHER_REVERSED_SOURCE_ROWS = {(2016,31), (2020,117), (2022,181)}
TOL = 1e-10


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def load_inputs(data_dir: Path = DATA):
    paths = [data_dir / 'poll_usages_2006_2012.csv',
             data_dir / 'poll_usages_2014_2020.csv',
             data_dir / 'poll_usages_2022.csv',
             data_dir / 'poll_usages_2024.csv']
    rows = [record for path in paths for record in read_csv(path)]
    expected_n = sum(EXPECTED_ROWS.values())
    if len(rows) != expected_n:
        raise ValueError(f'Expected {expected_n} frozen poll usages, found {len(rows)}')
    cycle_counts = Counter(int(r['cycle']) for r in rows)
    if cycle_counts != EXPECTED_ROWS:
        raise ValueError(f'Frozen poll-usage cycle counts differ: {cycle_counts}')
    keys = [(r['polling_signal_id'],r['source_cycle_file'],r['source_cycle_row_number'])
            for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate frozen usage key')
    labels = read_csv(data_dir / 'pollster_identity_2022_2024.csv')
    mapping = {(int(r['forecast_cycle']), r['raw_pollster_name']): r for r in labels}
    if len(mapping) != len(labels):
        raise ValueError('Duplicate 2022/2024 raw-label identity mapping')
    if Counter(int(r['forecast_cycle']) for r in labels) != {2022:64,2024:70}:
        raise ValueError('Frozen raw-label coverage differs')
    references = read_csv(data_dir / 'polling_signal_reference_2006_2024.csv')
    by_signal = {r['polling_signal_id']:r for r in references}
    if len(references)!=629 or len(by_signal)!=629:
        raise ValueError('Expected 629 unique historical/development/evaluation signals')
    if set(r['polling_signal_id'] for r in rows)!=set(by_signal):
        raise ValueError('Changed frozen signal eligibility universe')
    anomalies=[r for r in rows if r['source_data_anomaly']=='True']
    if {(r['polling_signal_id'], int(r['source_cycle_row_number'])) for r in anomalies} != {(s,ANOMALOUS_SOURCE_ROW) for s in ANOMALOUS_SIGNALS}:
        raise ValueError('Unexpected Arizona anomaly status or source row')
    return rows, mapping, references


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def make_row_weights(rows: list[dict[str,str]], mapping: dict,
                     quality_records: list[dict], *, quality_errors=None):
    quality = {(r['forecast_cycle'],r['reliability_pollster']):r for r in quality_records}
    # For known no-history fielders not present in the frozen audit-key universe,
    # verify no prior eligible error under that exact documented fielding identity.
    history = load_errors() if quality_errors is None else quality_errors
    first_history = defaultdict(int)
    for e in history:
        first_history[(e['cycle'],e['identity'])] += 1
    prepared=[]
    repeat_counts=Counter()
    for r in rows:
        cycle=int(r['cycle']);h=int(r['horizon_days'])
        if h not in HORIZONS:raise ValueError('Unexpected polling horizon')
        sid=r['polling_signal_id']
        raw=r['raw_pollster_name']; reliability=r['reliability_pollster']
        if not reliability or not r['v1_canonical_pollster']:
            raise ValueError(f'Missing identity for {sid} / {raw}')
        if cycle>=2022:
            match=mapping.get((cycle,raw))
            if match is None:
                raise ValueError(f'Unmatched frozen raw label {cycle} / {raw}')
            if match['reliability_pollster']!=reliability or match['identity_status']!=r['identity_status']:
                raise ValueError(f'Documentary identity crosswalk changed: {cycle} / {raw}')
            if int(match['reliability_data_through_cycle']) != cycle-2:
                raise ValueError(f'Quality vintage leak: {cycle} / {raw}')
        first,last,cut=map(_date,[r['poll_start_date'],r['poll_end_date'],r['cutoff_date']])
        anomaly = r['source_data_anomaly']=='True'
        reversed_dates=first>last
        if reversed_dates and not anomaly and (cycle,int(r['source_cycle_row_number'])) not in FROZEN_OTHER_REVERSED_SOURCE_ROWS:
            raise ValueError(f'Unexpected reversed source dates: {sid} / {raw}')
        if anomaly and not reversed_dates:
            raise ValueError(f'Anomaly flag without reversed dates: {sid}')
        if anomaly and not (cycle==2024 and sid in ANOMALOUS_SIGNALS and first==dt.date(2024,10,30) and last==dt.date(2024,10,2)):
            raise ValueError(f'Misidentified date anomaly: {sid}')
        # Half-day field-date precision (e.g., 3-day field window -> 1.5 day offset).
        median_age=(cut-first).days - (last-first).days/2
        repeat_bin=math.floor(median_age/14)
        repeat_key=(sid,r['v1_canonical_pollster'],repeat_bin)
        repeat_counts[repeat_key]+=1
        q_source=quality.get((cycle,reliability))
        if cycle<2022:
            if q_source is None:
                raise ValueError(f'Missing historical quality vintage: {cycle} / {reliability}')
        else:
            status=r['identity_status']
            if status=='MATCHED_HISTORY':
                if q_source is None or q_source['n_prior_polls']==0:
                    raise ValueError(f'Absent positive prior history: {cycle} / {reliability}')
            elif status=='CONFIRMED_NO_HISTORY':
                if q_source is not None and q_source['n_prior_polls']!=0:
                    raise ValueError(f'No-history identity has prior records: {cycle} / {reliability}')
                if any(e_cycle<cycle and eid==reliability and n>0 for (e_cycle,eid),n in first_history.items()):
                    raise ValueError(f'Claimed no-history fielding identity appears in eligible history: {reliability}')
            else:
                raise ValueError(f'Unresolved or invalid identity status: {cycle} / {raw}: {status}')
        q= q_source['quality_multiplier_p2'] if q_source is not None else 1.0
        if cycle>=2022 and abs(q-float(mapping[(cycle,raw)]['frozen_quality_multiplier_p2']))>TOL:
            raise AssertionError(f'Quality map does not match reconstructed audit: {cycle} / {raw}')
        n=float(r['sample_size']) if r['sample_size'] else 600.
        if not math.isfinite(n) or n<=0:raise ValueError('Invalid sample size')
        prepared.append(dict(r, **{'median_poll_age_days':median_age,'repeat_bin':repeat_bin,
                    '_repeat_key':repeat_key, '_effective_n':min(n,5000.),
                    'source_date_reversal_detected':reversed_dates,
                    'sample_fallback_used':not bool(r['sample_size']),
                    'quality_multiplier_p2':q}))
    result=[]
    for r in prepared:
        h=int(r['horizon_days']);age=r['median_poll_age_days']
        recency=2**(-age/(14+0.2*h))
        sample=math.sqrt(r['_effective_n']/600.)
        repeated=1./repeat_counts[r['_repeat_key']]
        v1=recency*sample*repeated
        q=r['quality_multiplier_p2'];p2=v1*q
        row={k:v for k,v in r.items() if not k.startswith('_')}
        row.update(w_recency=recency,w_sample=sample,w_repeat=repeated,
                   repeat_bin_count=repeat_counts[r['_repeat_key']],
                   v1_poll_weight=v1,v2_p2_poll_weight=p2)
        if abs(v1-float(r['frozen_v1_poll_weight']))>TOL or abs(p2-float(r['frozen_v2_p2_poll_weight']))>TOL or abs(q-float(r['frozen_quality_multiplier_p2']))>TOL:
            raise AssertionError(f'Frozen row-weight discrepancy: {r["polling_signal_id"]} / {r["poll_source_identifier"]}: {v1} / {p2}')
        result.append(row)
    return result


def aggregate(rows:list[dict], references:list[dict]):
    group=defaultdict(list)
    for r in rows:group[r['polling_signal_id']].append(r)
    results=[];max_abs={'v2_weight':0.,'v1_margin':0.,'v2_margin':0.,'max_share':0.}
    for ref in references:
        sid=ref['polling_signal_id'];polls=group[sid]
        if len(polls)!=int(ref['poll_count']):raise AssertionError(f'Frozen poll count changed: {sid}')
        w1=[x['v1_poll_weight'] for x in polls];w2=[x['v2_p2_poll_weight'] for x in polls];m=[float(x['poll_margin']) for x in polls]
        total1=math.fsum(w1);total2=math.fsum(w2)
        if min(total1,total2)<=0:raise ValueError('Nonpositive total weight')
        margin1=math.fsum(w*x for w,x in zip(w1,m))/total1
        margin2=math.fsum(w*x for w,x in zip(w2,m))/total2
        share=max(w2)/total2
        for key,calc,raw in [('v2_weight',total2,'frozen_v2_p2_total_weight'),
                 ('v1_margin',margin1,'frozen_v1_weighted_poll_margin'),
                 ('v2_margin',margin2,'frozen_v2_p2_weighted_poll_margin'),
                 ('max_share',share,'frozen_v2_p2_max_single_poll_weight_share')]:
            error=abs(calc-float(ref[raw]));max_abs[key]=max(max_abs[key],error)
            if error>1e-8:raise AssertionError(f'Frozen signal difference: {sid} {key} {error}')
        distinct=len({p['v1_canonical_pollster'] for p in polls})
        if ref['frozen_distinct_pollsters'] and distinct!=int(ref['frozen_distinct_pollsters']):
            raise AssertionError(f'Frozen original-canonical pollster count differs: {sid}')
        results.append(dict(polling_signal_id=sid,cycle=int(ref['cycle']),horizon_days=int(ref['horizon_days']),
               poll_count=len(polls),distinct_v1_canonical_pollsters=distinct,
               v1_total_weight=total1,v1_weighted_poll_margin=margin1,
               v2_p2_total_weight=total2,v2_p2_weighted_poll_margin=margin2,
               v2_p2_max_single_poll_weight_share=share,
               source_data_anomaly_present=any(x['source_data_anomaly']=='True' for x in polls)))
    return results,max_abs


def run(data_dir:Path=DATA):
    source,mapping,reference=load_inputs(data_dir)
    errors=load_errors(data_dir/'historical_reliability_errors.csv')
    frozen=load_reference(data_dir/'historical_quality_reference.csv')
    quality=reconstruct(errors,frozen)
    quality_check=verify_frozen(quality,frozen)
    rows=make_row_weights(source,mapping,quality,quality_errors=errors)
    signals,maximum=aggregate(rows,reference)
    counts=Counter(int(x['cycle']) for x in signals)
    expected={2006:33,2008:69,2010:70,2012:79,2014:98,2016:69,2018:70,2020:43,2022:38,2024:60}
    if counts!=expected:raise AssertionError(f'Unexpected signal counts {counts}')
    repeat=Counter(x['repeat_bin_count'] for x in rows)
    return rows,signals,{'poll_usages':len(rows),'signals':len(signals),
            'usages_by_cycle':dict(Counter(int(x['cycle']) for x in rows)),
            'signals_by_cycle':dict(counts),'repeat_bin_counts':dict(repeat),
            'max_signal_abs_difference':maximum,'historical_quality_audit':quality_check,
            'source_anomalies':sum(x['source_data_anomaly']=='True' for x in rows),
            'all_reversed_date_usages':sum(x['source_date_reversal_detected'] for x in rows)}


def export_csv(path:Path, data:list[dict]):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]),extrasaction='ignore');w.writeheader();w.writerows(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows-csv',type=Path)
    parser.add_argument('--signals-csv',type=Path)
    parser.add_argument('--json',type=Path)
    args=parser.parse_args()
    rows,signals,summary=run()
    if args.rows_csv:export_csv(args.rows_csv,rows)
    if args.signals_csv:export_csv(args.signals_csv,signals)
    report=json.dumps(summary,indent=2,sort_keys=True)+'\n'
    print(report,end='')
    if args.json:
        args.json.parent.mkdir(parents=True,exist_ok=True)
        args.json.write_text(report,encoding='utf-8')


if __name__=='__main__':main()
