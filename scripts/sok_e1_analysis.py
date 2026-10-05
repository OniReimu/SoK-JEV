"""E1: task/batch-stratified timing and real slot occupancy; no new measurements."""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from sok_6g_analysis import rq3_primary
from sok_cross_study_figures import style, export, COLORS, STYLES, MARKERS

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'artifacts/sok/cross-study'
OUT=ROOT/'artifacts/sok/e1'
EDGE=ROOT/'data/source/sok/cross-study/edge'
SIXG=ROOT/'data/source/sok/cross-study/6g'
BUDGETS=[.01,.1,1.,10.]
HASHES={}


def jl(p):
    raw=p.read_bytes();HASHES[str(p.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
    return [json.loads(s) for s in raw.splitlines() if s.strip()]


def timestamp(value):
    if isinstance(value,(int,float)):return float(value)
    if isinstance(value,str):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    return None


def block_ratio_ci(times,numerators,denominator=None,width=30):
    """Ratio of totals, resampling whole occupied time blocks; conditional on this trace."""
    if any(t is None for t in times):
        return dict(ci95=None,time_blocks=0,block_width_s=width,reason='missing actual timestamps')
    times=np.array(times,dtype=float)
    denom=np.ones(len(times)) if denominator is None else np.array(denominator,dtype=float)
    values=np.array(numerators,dtype=float)
    ids=np.floor((times-times.min())/width).astype(int)
    block_ids=sorted(set(ids));n_blocks=len(block_ids)
    if n_blocks<2:
        return dict(ci95=None,time_blocks=n_blocks,block_width_s=width,reason='fewer than two occupied time blocks')
    ns=np.array([values[ids==k].sum() for k in block_ids]);ds=np.array([denom[ids==k].sum() for k in block_ids])
    rng=np.random.default_rng(42);samples=rng.integers(0,n_blocks,(10000,n_blocks))
    num=ns[samples].sum(axis=1);den=ds[samples].sum(axis=1)
    keep=den>0
    assert keep.any()
    values=num[keep]/den[keep]
    return dict(ci95=np.quantile(values,[.025,.975]).tolist(),time_blocks=n_blocks,block_width_s=width,
                thin_time_coverage=n_blocks<8,discarded_zero_denominator_draws=int((~keep).sum()))


def endpoint_probabilities(rows,times):
    result={}
    for budget in BUDGETS:
        response=np.array([r['latency_s'] is not None and r['latency_s']<=budget for r in rows],dtype=float)
        validated=np.array([bool(r['valid']) and bool(v) for r,v in zip(rows,response)],dtype=float)
        result[str(budget)]=dict(response_elapsed_probability=float(response.mean()),
           validated_return_probability=float(validated.mean()),
           response_elapsed_ci=block_ratio_ci(times,response),validated_return_ci=block_ratio_ci(times,validated),
           sensitivity={str(w):block_ratio_ci(times,validated,width=w) for w in [60,120]})
    return result


def fixed_timing():
    records=jl(SOURCE/'records.jsonl')
    # Bundled-request timing is a separate task, never a field-count comparison.
    for path in sorted((EDGE/'hf/runs/EXP-2026-001/RQ1b').glob('*/ledger.jsonl')):
        input_path=EDGE/'hf/data/edgebench/v1/RQ1b'/path.parent.name/'test.jsonl'
        input_sha=hashlib.sha256(input_path.read_bytes()).hexdigest()
        HASHES[str(input_path.relative_to(ROOT))]=input_sha
        for i,row in enumerate(jl(path),1):
            if row.get('repeat',0)!=0:continue
            assert row['cases_sha256']==input_sha
            records.append(dict(study='Edge',task='RQ1b',condition=row['condition'],method=row['model'],
                platform=row['platform'],collection_phase=row['run_id'],valid=bool(row['valid']),
                latency_s=row['latency_s'],recorded_at=row['t_send_wall'],
                source=str(path.relative_to(ROOT))+':'+str(i)))
    return timing_strata(records),records


def timing_strata(records):
    groups=defaultdict(list)
    for r in records:
        source=r['source'].split('#',1)[0]
        # Locators with :line are JSONL; the source batch is explicit in the record for 6G.
        source=source.rsplit(':',1)[0] if source.rsplit(':',1)[-1].isdigit() else source
        phase=r.get('collection_phase') or str(Path(source).parent)
        groups[r['study'],r['task'],r['condition'],r['method'],r['platform'],phase].append(r)
    out=[]
    for key,rows in sorted(groups.items()):
        times=[timestamp(r['recorded_at']) for r in rows]
        order=sorted(range(len(rows)),key=lambda i: times[i] if times[i] is not None else i)
        rows=[rows[i] for i in order];times=[times[i] for i in order]
        lat=[r['latency_s'] for r in rows if r['latency_s'] is not None]
        result=dict(zip(['study','task','condition','method','platform','collection_phase'],key))
        result['selection_basis']=('Published per-case first HTTP 200 primary attempt; latency is attempt-level, not a reconstructed retry chain'
            if key[0]=='6G' and key[1]=='C1' and key[3]=='Qwen3.8-Flash' else
            'Frozen selected primary records in this original task/batch; extra collection attempts remain in source')
        result.update(n=len(rows),observed_latency_n=len(lat),p50_s=float(np.median(lat)) if lat else None,
          p95_s=float(np.quantile(lat,.95)) if lat else None,p99_descriptive_s=float(np.quantile(lat,.99)) if lat else None,
          probabilities=endpoint_probabilities(rows,times),actual_timestamp_n=sum(t is not None for t in times),
          source_ids=[r['source'] for r in rows],endpoint='client elapsed return; schema-valid return separately; no semantic/service claim')
        out.append(result)
    return out


def describe(values):
    values=[float(v) for v in values if v is not None and math.isfinite(v)]
    return dict(n=len(values),p50_s=float(np.median(values)) if values else None,
                p95_s=float(np.quantile(values,.95)) if values else None)


def physical_paths():
    """Observed native milestones; KPM is an upper bound, not verified service success."""
    out=[]
    for path in sorted((EDGE/'hf/runs/EXP-2026-002/rq5b').glob('*/seed_1/*/outcomes.jsonl')):
        rows=jl(path);ip=path.with_name('integrity.json')
        HASHES[str(ip.relative_to(ROOT))]=hashlib.sha256(ip.read_bytes()).hexdigest()
        integrity=json.loads(ip.read_text());assert integrity['complete'] and len(rows)==240
        arrivals=[r['arrival'] for r in rows]
        success=np.array([bool(r['correct_completion']) for r in rows],dtype=float)
        supported=np.array([bool(r['score']['supported']) for r in rows],dtype=float)
        assert int(success.sum())==integrity['correct_completion_count']
        assert int(supported.sum())==integrity['supported_arrivals']
        assert math.isclose(float(success.mean()),integrity['completion_rate_all'],abs_tol=1e-10)
        assert math.isclose(float(success.sum()/supported.sum()),integrity['completion_rate'],abs_tol=1e-10)
        def elapsed(r,end,start):
            return r[end]-r[start] if r.get(end) is not None and r.get(start) is not None else None
        stages={name:describe([elapsed(r,end,start) for r in rows]) for name,end,start in [
            ('decision_queue','decision_start','arrival'),('decision_slot','decision_end','decision_start'),
            ('return_from_arrival','decision_end','arrival'),('service_queue','service_dispatch','service_enqueued'),
            ('dispatch_to_terminal','terminal','service_dispatch')]}
        stages['all_terminal']=describe([r['terminal']-r['arrival'] for r in rows])
        stages['correct_service_terminal']=describe([r['terminal']-r['arrival'] for r in rows if r['correct_completion']])
        out.append(dict(study='Edge',task='RQ5b',method=integrity['model'],condition=integrity['condition'],
          collection_phase=path.parent.relative_to(EDGE/'hf/runs/EXP-2026-002/rq5b').as_posix(),
          n=240,supported_n=int(supported.sum()),correct_service_n=int(success.sum()),
          cache_hits=sum(bool(r['cache_hit']) for r in rows),observed_lambda=239/(max(arrivals)-min(arrivals)),
          stages=stages,correct_all_probability=float(success.mean()),
          correct_supported_probability=float(success.sum()/supported.sum()),
          correct_all_ci=block_ratio_ci(arrivals,success),correct_supported_ci=block_ratio_ci(arrivals,success,supported),
          sensitivity={str(w):block_ratio_ci(arrivals,success,supported,width=w) for w in [60,120]},
          endpoint='real OCR correct completion; all terminal events include failures/unsupported; API actuation acknowledgement unavailable',
          source_ids=[str(path.relative_to(ROOT)),str(ip.relative_to(ROOT))]))
    for path in sorted((SIXG/'hf/runs/c3-real-stack').glob('c3main-*/records.jsonl')):
        rows=jl(path);ip=path.with_name('integrity.json')
        HASHES[str(ip.relative_to(ROOT))]=hashlib.sha256(ip.read_bytes()).hexdigest()
        integrity=json.loads(ip.read_text());assert integrity['status']=='PASS' and len(rows)==30
        stages={field:describe([r.get(field) for r in rows]) for field in ['ell_s','delta_a1_s','delta_e2_s','kpm_change_upper_bound_s']}
        for name,end in [('decision_wall','t_decision_returned'),('Ta_gnb_ack','t_gnb_acknowledged'),('Tb_kpm_upper','t_first_kpm_change')]:
            stages[name]=describe([timestamp(r[end])-timestamp(r['t_intent_issued']) if r.get(end) else None for r in rows])
        for field in ['ell_s','delta_a1_s','delta_e2_s','kpm_change_upper_bound_s']:
            assert stages[field]['n']==integrity['summary'][field]['n']
            assert math.isclose(stages[field]['p50_s'],integrity['summary'][field]['median_s'],abs_tol=1e-9)
        out.append(dict(study='6G',task='C3',method=integrity['interpreter'],condition='real_stack',
          collection_phase=path.parent.name,n=30,stages=stages,
          endpoint='gNB acknowledgement and observed KPM upper bound; adapter ell differs from whole decision wall interval; no causal service verification',
          source_ids=[str(path.relative_to(ROOT)),str(ip.relative_to(ROOT))]))
    assert len(out)==63
    for task,folder in [('policy','rq1-scale-20260923'),('service','service-scale-20260923'),('route','route-holdout-01')]:
        index_path=ROOT/'artifacts/sok'/folder/'online-source.json'
        HASHES[str(index_path.relative_to(ROOT))]=hashlib.sha256(index_path.read_bytes()).hexdigest()
        groups=defaultdict(list)
        for entry in json.loads(index_path.read_text()):
            path=ROOT/entry['source'];raw=path.read_bytes()
            HASHES[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
            row=json.loads(raw);assert entry['total_s']==row['total_s']
            groups[entry['condition'],entry['method'],str(path.parent)].append((entry,row))
        for (condition,method,batch),items in sorted(groups.items()):
            fields=['observation_s','selection_s','refresh_s','installation_s','verification_s',
                    'execution_s','fallback_s','canary_s','total_s']
            stages={f:describe([raw.get(f) for _,raw in items]) for f in fields if any(f in raw for _,raw in items)}
            out.append(dict(study='SoK',task=task,method=method,condition=condition,n=len(items),
              collection_phase=str(Path(batch).relative_to(ROOT)),stages=stages,
              direct_success_n=sum(bool(e['direct']) for e,_ in items),
              final_success_n=sum(bool(e['final']) for e,_ in items),
              endpoint='small serial execution subset; final includes fallback; durations only, no actual t0 for time-block inference, no imposed open arrival rate',
              source_ids=[e['source'] for e,_ in items]))
    return out


def loads():
    out=[]
    config_path=SIXG/'github/data/ranbench/ranintent-v1/config.json'
    HASHES[str(config_path.relative_to(ROOT))]=hashlib.sha256(config_path.read_bytes()).hexdigest()
    cmap=json.loads(config_path.read_text())['c2_class_map']
    def installable(row):
        policy=row.get('policy') if row.get('valid') else None
        if not policy or policy.get('action') not in ['prioritise','deprioritise','revert_default']:return False
        if policy.get('scope') not in ['north_cluster','south_cluster','stadium','hospital_zone','all_cells']:return False
        if cmap.get(policy.get('class')) is None:return False
        return policy['action']=='revert_default' or policy.get('priority') in ['critical','high','normal','low']
    for path in sorted((EDGE/'hf/runs/EXP-2026-002/rq5a').glob('load_*/seed_1/*/admission.jsonl')):
        records=sorted(jl(path),key=lambda r:r['id'])
        outcomes=sorted(jl(path.with_name('outcomes.jsonl')),key=lambda r:r['id'])
        assert len(records)==len(outcomes)==300
        assert [r['id'] for r in records]==[r['id'] for r in outcomes]
        rate=float(path.parts[-4].split('_')[1]);slots=4
        arrivals=[r['arrival'] for r in records]
        service=np.array([r['decision_end']-r['decision_start'] if r.get('decision_start') is not None and r.get('decision_end') is not None else 0 for r in records])
        dispatched=np.array([r.get('decision_start') is not None and r.get('decision_end') is not None for r in records],dtype=float)
        if dispatched.sum()==0:
            mean_s=0.;rho=0.;rho_ci=None
        else:
            assert all(s>=0 for s in service)
            mean_s=float(service.sum()/dispatched.sum());rho=rate*mean_s/slots
            estimate=block_ratio_ci(arrivals,service,dispatched)
            rho_ci=None if estimate['ci95'] is None else [v*rate/slots for v in estimate['ci95']]
        end_budget=2.
        success=np.array([r['status']=='success' for r in outcomes],dtype=float)
        returned=np.array([r.get('predicted') is not None and r.get('decision_end') is not None and
                           r['decision_end']-r['arrival']<=end_budget for r in records],dtype=float)
        queue=[r['queue_wait_s'] for r in records if r.get('queue_wait_s') is not None]
        out.append(dict(study='Edge',task='RQ5a',method=path.parts[-2],condition=path.parts[-4],
          collection_phase='seed_1/'+path.parts[-2],n_arrivals=300,n_dispatched=int(dispatched.sum()),
          offered_lambda=rate,observed_lambda=299/(max(arrivals)-min(arrivals)),slots=slots,mean_slot_s=mean_s,
          rho_offered=rho,rho_ci95=rho_ci,
          rho_accepted=(float(dispatched.sum())/(max(arrivals)-min(arrivals)))*mean_s/slots,
          native_budget_s=end_budget,native_attainment=float(success.mean()),native_attainment_ci=block_ratio_ci(arrivals,success),
          validated_return_by_native_budget=float(returned.mean()),validated_return_ci=block_ratio_ci(arrivals,returned),
          queue_observed_n=len(queue),queue_p50_s=float(np.median(queue)) if queue else None,
          queue_p95_s=float(np.quantile(queue,.95)) if queue else None,
          block_sensitivity={str(w):dict(native=block_ratio_ci(arrivals,success,width=w),
            slot_service=block_ratio_ci(arrivals,service,dispatched,width=w)) for w in [60,120]},
          rho_interpretation='offered-demand proxy using service times of dispatched calls; rejection prevents identifying all-arrival service demand',
          native_endpoint='strict correct and on-time modeled service; measured live admission',source_ids=[str(path.relative_to(ROOT)),str(path.with_name('outcomes.jsonl').relative_to(ROOT))]))
    for item in rq3_primary(SIXG):
        records=item['trace'];ip=item['path'].with_name('integrity.json');integrity=item['integrity']
        HASHES[str(item['path'].relative_to(ROOT))]=hashlib.sha256(item['path'].read_bytes()).hexdigest()
        HASHES[str(ip.relative_to(ROOT))]=hashlib.sha256(ip.read_bytes()).hexdigest()
        arrivals=[r['arrival_s'] for r in records]
        services=[r['service_latency_s'] for r in records];slots=integrity['slots'];rate=integrity['rate_per_s']
        rho=rate*float(np.mean(services))/slots
        ci=block_ratio_ci(arrivals,services);rho_ci=None if ci['ci95'] is None else [v*rate/slots for v in ci['ci95']]
        pub=item['published'];delay_a1=float(pub['delta_a1_s']);delay_e2=float(pub['delta_e2_s'])
        # Published schedule requires an installable action, not merely schema-valid refresh/decline.
        eligible=np.array([installable(r) for r in records])
        # Confirm the exact endpoint against released per-cell values before using it.
        total=np.array([r['latency_s']+r['queue_wait_s']+delay_a1+delay_e2 for r in records])
        attained=eligible & (total<=1.)
        if not math.isclose(float(attained.mean()),float(pub['share_enforced_within_1s']),abs_tol=1e-10):
            raise ValueError(f"6G schedule endpoint mismatch: {item['path']}; review install mapping before analysis")
        validated=np.array([bool(r['valid']) and r['completion_s']-r['arrival_s']<=1. for r in records])
        wait=[r['queue_wait_s'] for r in records]
        out.append(dict(study='6G',task='RQ3',method=pub['model'],condition='rate_'+pub['rate_per_s'],
          collection_phase=item['path'].parent.relative_to(SIXG/'hf/runs/rq3-load-traces').as_posix(),
          n_arrivals=300,n_dispatched=300,offered_lambda=rate,observed_lambda=299/(max(arrivals)-min(arrivals)),
          slots=slots,mean_slot_s=float(np.mean(services)),rho_offered=rho,rho_ci95=rho_ci,
          rho_accepted=(299/(max(arrivals)-min(arrivals)))*float(np.mean(services))/slots,
          native_budget_s=1.,native_attainment=float(attained.mean()),native_attainment_ci=block_ratio_ci(arrivals,attained),
          validated_return_by_native_budget=float(validated.mean()),validated_return_ci=block_ratio_ci(arrivals,validated),
          queue_observed_n=300,queue_p50_s=float(np.median(wait)),queue_p95_s=float(np.quantile(wait,.95)),
          block_sensitivity={str(w):dict(native=block_ratio_ci(arrivals,attained,width=w),
            slot_service=block_ratio_ci(arrivals,services,width=w)) for w in [60,120]},
          rho_interpretation='empirical offered utilization within the measured four-slot trace',
          native_endpoint='scheduled installable policy plus documented A1/E2 delays; not measured radio success',
          source_ids=[str(item['path'].relative_to(ROOT)),str(ip.relative_to(ROOT))]))
        assert math.isclose(rho,float(pub['rho']),abs_tol=1e-9)
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixed,records=fixed_timing();print('E1 fixed strata',len(fixed),flush=True)
    online=loads();print('E1 load cells',len(online),flush=True)
    paths=physical_paths();print('E1 physical-path cells',len(paths),flush=True)
    result=dict(status='E1_REANALYSIS_COMPLETE',date='2026-10-03',seed=42,bootstrap_draws=10000,
      time_blocks_s=[30,60,120],fixed=fixed,loads=online,physical_paths=paths,
      limits=['No pooled engine-class distributions or provider reliability claims.',
              '6G C1 Qwen3.8 primary selection is per-case first HTTP 200; its timing is conditional on selected attempts, not original-attempt/retry-chain turnaround.',
              'Sparse occupied time blocks cannot establish long-run stationarity.',
              'Edge offered rho uses observed dispatched service, not unidentified service of rejected arrivals.',
              'SoK fixed/serial online subsets have no independently imposed open arrival rate; rho unavailable.',
              '6G scheduled enforcement and Edge modeled service are different native endpoints.'],
      source_records_sha256=HASHES[str((SOURCE/'records.jsonl').relative_to(ROOT))])
    (OUT/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    from sok_e1_figures import render, tables
    render(result,records,OUT);tables(result,OUT)
    (OUT/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for p in [Path(__file__),Path(__file__).with_name('sok_e1_figures.py'),Path(__file__).with_name('sok_6g_analysis.py')]:
        HASHES[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT/'source-manifest.json').write_text(json.dumps(dict(sources=HASHES,new_model_calls=0,
       predecessor_manifest='artifacts/sok/cross-study/source-manifest.json'),indent=2)+'\n')


if __name__=='__main__':main()
