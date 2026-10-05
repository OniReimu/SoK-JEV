"""Validate real slot occupancy; finite-window paired time-block analysis of replay."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np

BOOT = 10000
BUDGETS = [.5,1.,2.,5.,10.]


def jl(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def ci(values):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    return np.quantile(v,[.025,.975]).tolist() if len(v) else None


def median_or_none(values):
    v = np.asarray(values,dtype=float)
    v = v[np.isfinite(v)]
    return float(np.median(v)) if len(v) else None


def block_draws(n):
    idx = np.random.default_rng(42).integers(0,n,(BOOT,n))
    return np.asarray([np.bincount(row,minlength=n) for row in idx])


def weighted_quantiles(values, blocks, weights):
    """Same linear sample quantile as explicitly repeating the sampled blocks."""
    values = np.asarray(values,dtype=float)
    ok = np.isfinite(values)
    if not ok.any():
        return np.full((2,len(weights)),np.nan)
    order = np.argsort(values[ok],kind='stable')
    v = values[ok][order]
    b = np.asarray(blocks)[ok][order]
    result = np.full((2,len(weights)),np.nan)
    for begin in range(0,len(weights),250):
        w = weights[begin:begin+250,b]
        sums = np.cumsum(w,axis=1)
        n = sums[:,-1]
        live = n > 0
        for k,q in enumerate([.5,.95]):
            pos = (n-1)*q
            lo = np.floor(pos).astype(int)
            hi = np.ceil(pos).astype(int)
            ilo = (sums > lo[:,None]).argmax(axis=1)
            ihi = (sums > hi[:,None]).argmax(axis=1)
            out = v[ilo]+(v[ihi]-v[ilo])*(pos-lo)
            out[~live] = np.nan
            result[k,begin:begin+len(w)] = out
    return result


def describe(values, blocks, weights):
    a = np.asarray(values,dtype=float)
    valid = a[np.isfinite(a)]
    if not len(valid):
        return dict(observed_n=0,p50_s=None,p95_s=None,ci95_p50_s=None,ci95_p95_s=None)
    boot = weighted_quantiles(a,blocks,weights)
    return dict(observed_n=len(valid),p50_s=float(np.median(valid)),p95_s=float(np.quantile(valid,.95)),
                ci95_p50_s=ci(boot[0]),ci95_p95_s=ci(boot[1]))


def ratio(flags,blocks,weights):
    nblocks = weights.shape[1]
    den = np.bincount(blocks,minlength=nblocks)
    num = np.bincount(blocks,weights=np.asarray(flags,dtype=float),minlength=nblocks)
    ds = weights @ den
    ns = weights @ num
    live = ds > 0
    return dict(numerator=int(num.sum()),denominator=int(den.sum()),value=float(num.sum()/den.sum()),
                ci95=ci(ns[live]/ds[live]))


def check_cell(rows, planned, arrivals, condition, config):
    assert [r['arrival_id'] for r in rows] == list(range(len(planned))), 'Missing, duplicate, or reordered arrivals'
    assert [r['id'] for r in arrivals] == list(range(len(planned))), 'Incomplete observed arrival trace'
    previous = -float('inf')
    for r, event, actual in zip(rows,planned,arrivals):
        assert r['t0'] == actual['t0']
        assert r['scheduled_offset_s'] == event['scheduled_offset_s']
        assert r['t0'] <= r['tq'] <= r['td'] <= r['t_release']
        assert previous <= r['tq'], 'Decision slots overlapped within c=1 cell'
        previous = r['t_release']
        for key,end,start in [('queue_s','tq','t0'),('D_s','td','tq'),('slot_s','t_release','tq')]:
            assert abs(r[key]-(r[end]-r[start])) < 1e-8
        assert r['D_s'] >= r['requested_D_s']-.001, 'Injected delay escaped the decision slot'
        if condition['type'] == 'controlled':
            assert r['requested_D_s'] == condition['D_s']
        else:
            i = r['empirical_source_index']
            assert r['requested_D_s'] == condition['support'][i]['D_s']
        assert set(r['replay']) == set(config['physical']), 'Missing replay domain'
        for domain, replay in r['replay'].items():
            assert replay['physical_index'] == event['physical_indices'][domain]
            src = config['physical'][domain][replay['physical_index']]
            assert replay['source_status'] == src['status']
            for endpoint,field in [('Ta_s','acknowledgement_s'),('Tb_s','verified_outcome_s')]:
                if src[field] is None:
                    assert replay[endpoint] is None
                else:
                    assert abs(replay[endpoint]-(r['td']-r['t0']+src[field])) < 1e-8
            if 'observation' in src:
                observation = src['observation']
                assert replay['unreached_endpoints'] == observation['unreached_endpoints']
                assert replay['source_error'] == observation['error']
                assert abs(replay['observed_until_s']-(r['td']-r['t0']+
                           observation['postdecision_observed_until_s'])) < 1e-8


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--check-only',action='store_true')
    a = p.parse_args()
    config = json.loads((a.run/'inputs.json').read_text())
    state = json.loads((a.run/'status.json').read_text())
    manifest = json.loads((a.run/'manifest.json').read_text())
    assert hashlib.sha256((a.run/'inputs.json').read_bytes()).hexdigest() == manifest['inputs_sha256']
    assert hashlib.sha256((a.run/'measurement-code.py').read_bytes()).hexdigest() == manifest['code_sha256']
    formal = config['purpose'] == 'formal_load_replay'
    if formal:
        assert all('observation' in p for records in config['physical'].values() for p in records)
    assert state['phase'] == ('LOAD_EXECUTION_COMPLETE_ANALYSIS_PENDING' if formal else 'DIAGNOSTIC_COMPLETE')
    assert formal or a.check_only, 'Synthetic diagnostic must not produce formal analysis'
    plan = json.loads((a.run/'arrival-plan.json').read_text())
    arrival_rows = jl(a.run/'arrivals.jsonl')
    arrivals = {i:[r for r in arrival_rows if r['rate_index']==i] for i in range(3)}
    conditions = {c['id']:c for c in config['controlled']+config['empirical']}
    assert len(conditions) == len(config['controlled'])+len(config['empirical']), 'Duplicate condition ID'
    expected_cells = {'r'+str(i)+'-'+cid for i in range(3) for cid in conditions}
    assert set(state['cells']) == expected_cells, 'Incomplete queue-condition matrix'
    if formal:
        assert len(config['empirical']) == 24 and len(config['controlled']) == 4
    result = dict(status='PASS_QUEUE_TIMELINE_CHECK' if a.check_only else 'E2_LOAD_REPLAY_ANALYZED',
        purpose=config['purpose'], cells=[], comparisons=[], input_sha256=manifest['inputs_sha256'],
        source_run=str(a.run.resolve()),
        source_sha256={name:hashlib.sha256((a.run/name).read_bytes()).hexdigest()
                       for name in ['status.json','manifest.json','arrival-plan.json','arrivals.jsonl','baseline.json']},
        measurement_code_sha256=manifest['code_sha256'],
        analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limits=['Real imposed-service queues followed by replayed execution residuals.',
                'One finite arrival trace per load, not independent seeds or production traffic.',
                'Overloaded queues are nonstationary; block intervals describe the observed window.',
                'Client-return timing replay says nothing about semantics or hosted concurrency.',
                'Verified endpoint quantiles condition on observed source outcomes; all arrivals remain in budget denominators.',
                'Failed-action observation durations are replayed and retained separately, never treated as completion times.'])
    weights = block_draws(config['measured_blocks']) if not a.check_only else None
    values_by_cell = {}
    checked = 0
    for cell_id, status in sorted(state['cells'].items()):
        rows = jl(a.run/(cell_id+'.jsonl'))
        i = status['rate_index']
        condition = conditions[status['condition_id']]
        assert status['completed'] == status['expected'] == len(rows) == len(plan['traces'][i])
        assert abs(status['lambda_per_s'] - config['baseline_rhos'][i]/state['baseline_mean_slot_s']) < 1e-8
        check_cell(rows,plan['traces'][i],arrivals[i],condition,config)
        checked += len(rows)
        if a.check_only:
            continue
        measured = [r for r in rows if r['scheduled_offset_s'] >= config['warmup_s']]
        blocks = np.asarray([int((r['scheduled_offset_s']-config['warmup_s'])/config['block_width_s']) for r in measured])
        assert set(blocks) == set(range(config['measured_blocks'])), 'All 20 observed time blocks required'
        values_by_cell[cell_id] = measured
        slot = np.asarray([r['slot_s'] for r in measured])
        delay = np.asarray([r['D_s'] for r in measured])
        queue = np.asarray([r['queue_s'] for r in measured])
        rate = status['lambda_per_s']
        base = dict(cell_id=cell_id,condition=condition['id'],type=condition['type'],
            identity=condition.get('identity'),requested_D_s=condition.get('D_s'),
            baseline_rho=status['baseline_rho'],lambda_per_s=rate,slots=1,
            observed_lambda_per_s=(len(arrivals[i])-1)/(arrivals[i][-1]['t0']-arrivals[i][0]['t0']),
            postwarm_arrivals=len(measured),mean_slot_s=float(slot.mean()),rho=float(rate*slot.mean()),
            necessary_capacity_condition_met=bool(rate*slot.mean()<1),
            D=describe(delay,blocks,weights),queue=describe(queue,blocks,weights),
            pending_at_arrival_horizon=sum(r['td']>state['epoch_monotonic']+state['horizon_s'] for r in rows),
            queue_p95_by_block=[float(np.quantile(queue[blocks==b],.95)) for b in range(config['measured_blocks'])],
            max_arrival_lag_s=max(r['arrival_lag_s'] for r in arrivals[i]),
            source_records_sha256=hashlib.sha256((a.run/(cell_id+'.jsonl')).read_bytes()).hexdigest(),
            domains={})
        for domain in ['edge','transport']:
            ta=np.asarray([r['replay'][domain]['Ta_s'] for r in measured],dtype=float)
            tb=np.asarray([r['replay'][domain]['Tb_s'] for r in measured],dtype=float)
            primary=dict(Ta=describe(ta,blocks,weights),Tb=describe(tb,blocks,weights),
                D_over_Ta_median=median_or_none(delay/ta),D_over_Tb_median=median_or_none(delay/tb),
                reference_budget_s=config['budgets_s'][domain],
                budgets={str(b):dict(Ta=ratio(np.isfinite(ta)&(ta<=b),blocks,weights),
                                    Tb=ratio(np.isfinite(tb)&(tb<=b),blocks,weights)) for b in BUDGETS})
            if formal:
                failed_wait = [r['replay'][domain]['observed_until_s']
                               if r['replay'][domain]['source_status'] != 'verified' else np.nan
                               for r in measured]
                primary['incomplete_observation_duration'] = describe(failed_wait, blocks, weights)
                primary['completion_counts'] = dict(acknowledged=int(np.isfinite(ta).sum()),
                    verified=int(np.isfinite(tb).sum()), unverified=int((~np.isfinite(tb)).sum()),
                    arrivals=len(measured))
            # Two adjacent primary blocks form each 20s sensitivity block.
            wide = blocks//2
            wide_weights = block_draws(config['measured_blocks']//2)
            primary['block20s_sensitivity']=dict(Tb=describe(tb,wide,wide_weights),
                budget_Tb=ratio(np.isfinite(tb)&(tb<=config['budgets_s'][domain]),wide,wide_weights))
            base['domains'][domain]=primary
        result['cells'].append(base)
    if not a.check_only:
        for cell in result['cells']:
            if cell['type']!='controlled' or cell['requested_D_s']==0:
                continue
            index=state['cells'][cell['cell_id']]['rate_index']
            fast=values_by_cell['r'+str(index)+'-controlled-0.0']
            slow=values_by_cell[cell['cell_id']]
            assert [r['arrival_id'] for r in fast]==[r['arrival_id'] for r in slow]
            blocks=np.asarray([int((r['scheduled_offset_s']-config['warmup_s'])/config['block_width_s']) for r in slow])
            delta=np.asarray([(s['td']-s['t0'])-(f['td']-f['t0']) for f,s in zip(fast,slow)])
            result['comparisons'].append(dict(cell_id=cell['cell_id'],baseline='same-rate D0',
                returned_endpoint_delta_s=describe(delta,blocks,weights),
                amplification_over_requested_D_median=float(np.median(delta)/cell['requested_D_s']),
                scope='Paired added decision and queue time; same replayed execution residual cancels.'))
    result.update(checked_queue_records=checked,checked_cells=len(state['cells']),
                  measured_blocks=config['measured_blocks'],block_width_s=config['block_width_s'])
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/('validation.json' if a.check_only else 'load-results.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ['status','checked_queue_records','checked_cells']}))


if __name__=='__main__':
    main()
