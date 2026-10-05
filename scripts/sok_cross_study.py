"""Offline, source-traced cross-study synthesis. Never executes experiment code."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import math
from sok_6g_analysis import c1_primary, rq3_primary

import numpy as np
from scipy.stats import binomtest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/sok/cross-study'
EDGE=ROOT/'data/source/sok/cross-study/edge'
SIXG=ROOT/'data/source/sok/cross-study/6g'
HASHES={}
ROWS=[]
CHECKS=Counter()
MODELS=['jev','deepseek','gemini','glm47','qwen']

def rel(p):return str(p.relative_to(ROOT))
def read(p):
    p=Path(p); raw=p.read_bytes();HASHES[rel(p)]=hashlib.sha256(raw).hexdigest()
    return json.loads(raw)
def lines(p):
    raw=p.read_bytes();HASHES[rel(p)]=hashlib.sha256(raw).hexdigest()
    return [json.loads(x) for x in raw.splitlines() if x.strip()]
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def wilson(k,n):
    z=1.959963984540054; p=k/n;den=1+z*z/n
    c=(p+z*z/(2*n))/den;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [0.0 if k==0 else max(0,c-h),1.0 if k==n else min(1,c+h)]
def summarize(rs):
    n=len(rs);q=sum(r['correct'] for r in rs);v=sum(r['valid'] for r in rs)
    lat=[r['latency_s'] for r in rs if r['latency_s'] is not None]
    return dict(n=n,correct=q,accuracy=q/n,accuracy_ci95=wilson(q,n),valid=v,valid_rate=v/n,
                valid_ci95=wilson(v,n),latency_n=len(lat),p50_s=float(np.median(lat)) if lat else None,
                p95_s=float(np.quantile(lat,.95)) if lat else None,
                invalid_n=n-v,source_ids=[r['source'] for r in rs],
                validated_return_budget_probability={str(b):sum(r['valid'] and r['latency_s'] is not None and r['latency_s']<=b for r in rs)/n for b in [.01,.1,1.,10.]})

def load_sok():
    paths=[('policy','artifacts/sok/rq1-scale-20260923/fixed-source.json'),
           ('service','artifacts/sok/service-scale-20260923/fixed-source.json'),
           ('route','artifacts/sok/route-holdout-01/fixed-source.json')]
    baseline_cache={}
    for task,path in paths:
        data=read(ROOT/path)
        for r in data:
            if task=='policy' and r['task']!='policy':continue
            p=ROOT/r['source']; rid=r.get('row_id',r['case']+'-'+r['condition'])
            if r['method'] in MODELS:
                raw=read(p)
                assert raw['row_id']==rid and raw['method']==r['method']
                assert raw['correct']==r['correct']==(raw.get('action') in raw['expected'])
                assert (raw['status']=='valid')==r['valid']
                assert abs(raw['elapsed_s']-r.get('elapsed_s',r.get('latency_s')))<1e-10
                CHECKS['sok_model_records_checked']+=1
                stamp=raw.get('started_at');model=raw.get('response_model') or raw.get('request',{}).get('model')
                provider=raw.get('provider')
                locator=r['source']
            else:
                if p not in baseline_cache:
                    baseline_cache[p]={(x['row_id'],x['method']):(i,x) for i,x in enumerate(read(p))}
                i,raw=baseline_cache[p][rid,r['method']]
                assert raw['correct']==r['correct'] and raw['action']==r['action']
                assert abs(raw['elapsed_s']-r.get('elapsed_s',r.get('latency_s')))<1e-10
                CHECKS['sok_baseline_records_checked']+=1
                stamp=None;model=r['method'];provider=None;locator=r['source']+'#item='+str(i)
            ROWS.append(dict(study='SoK',task=task,condition=r['condition'],method=r['method'],
                case=r['case'],stratum=r.get('stratum',r.get('family',r.get('regime','all'))),
                correct=r['correct'],valid=r['valid'],latency_s=r.get('elapsed_s',r.get('latency_s')),
                action=r.get('action'),nodes=r.get('n_nodes'),source=locator,recorded_at=stamp,
                resolved_model=model,provider=provider,platform='as-recorded',
                collection_phase=r.get('collection_phase'),field_error_rate=None))
    # Old contract batch: keep the documented Cloudflare GLM replacement, not
    # both the original GLM batch and its replacement.
    base=ROOT/'experiments/EXP-016-context-catalogue/contract-test-01'
    contract_inputs={r['row_id']:r for r in read(base/'frozen/inputs.json')}
    rawmap={}
    for folder,accept in [(base/'run',lambda r:r['method']!='glm47'),
                          (base/'cloudflare-unified-01/run',lambda r:r['method']=='glm47')]:
        for p in sorted(folder.glob('[0-9]*-*.json')):
            r=read(p)
            if accept(r):rawmap[r['row_id'],r['method']]=(p,r)
    bs={r['row_id']:(i,r) for i,r in enumerate(lines(base/'baselines/scores.jsonl'),1)}
    data=read(ROOT/'artifacts/sok/glm-cloudflare-unified-01/RQ4/contract-source.json')
    for r in data:
        if r['condition'] not in ['base','rekey','refresh','absent']:continue
        if r['method'] in MODELS:
            p,raw=rawmap[r['row_id'],r['method']]
            assert raw['correct']==r['correct']==(raw.get('action') in raw['expected'])
            assert abs(raw['elapsed_s']-r['elapsed_s'])<1e-10
            assert (raw['status']=='valid')==r['valid'];locator=rel(p)
            stamp=raw.get('started_at');model=raw.get('response_model');provider=raw.get('provider')
            CHECKS['sok_model_records_checked']+=1
        else:
            i,raw=bs[r['row_id']];v=raw[r['method']]
            assert r['action']==v['action'] and r['correct']==(v['action'] in raw['expected'])
            locator=rel(base/'baselines/scores.jsonl')+':'+str(i)
            stamp=None;model=r['method'];provider=None;CHECKS['sok_baseline_records_checked']+=1
        ROWS.append(dict(study='SoK',task='catalogue',condition=r['condition'],method=r['method'],
            case=r['case'],stratum=contract_inputs[r['row_id']]['family'],correct=r['correct'],valid=r['valid'],latency_s=r['elapsed_s'],
            action=r.get('action'),source=locator,recorded_at=stamp,resolved_model=model,provider=provider,
            platform='as-recorded',nodes=None,field_error_rate=None))
    load_catalogue_competition()


def load_catalogue_competition():
    """Table 10A uses two incoming candidates, distinct from the earlier refresh."""
    base=ROOT/'experiments/EXP-016-context-catalogue/contract-test-01/refresh-competition-01'
    inputs={r['row_id']:r for r in read(base/'frozen/inputs.json')}
    cf={r['row_id']:r for r in read(base/'cloudflare-unified-01/frozen/inputs.json')}
    assert set(inputs)==set(cf) and len(inputs)==48
    for key,row in inputs.items():
        assert row['text']==cf[key]['text'] and row['correct']==cf[key]['correct']
        state=json.loads(row['text'])
        assert len(set(state['current_catalogue'])-set(state['history'][0]['catalogue']))==2
    added=[]
    for folder in [base/'run',base/'cloudflare-unified-01/run']:
        for path in sorted(folder.glob('[0-9]*-*.json')):
            raw=read(path)
            # Keep the same complete Cloudflare replacement used in the old table.
            if (raw['method']=='glm47') != ('cloudflare-unified-01' in path.parts):
                continue
            case=inputs[raw['row_id']]
            assert raw['method'] in MODELS and raw['case']==case['case']
            assert raw['input_sha256']==hashlib.sha256(case['text'].encode()).hexdigest()
            assert raw['expected']==case['correct']
            assert raw['correct']==(raw.get('action') in case['correct'])
            added.append(dict(study='SoK',task='catalogue',condition='refresh_competition',
                method=raw['method'],case=case['case'],stratum=case['family'],
                correct=raw['correct'],valid=raw['status']=='valid',latency_s=raw['elapsed_s'],
                action=raw.get('action'),source=rel(path),recorded_at=raw.get('started_at'),
                resolved_model=raw.get('response_model'),provider=raw.get('provider'),
                platform='as-recorded',nodes=None,field_error_rate=None,
                collection_phase=rel(folder)))
    path=base/'baselines/scores.jsonl'
    for line,raw in enumerate(lines(path),1):
        case=inputs[raw['row_id']]
        assert raw['expected']==case['correct'] and raw['family']==case['family']
        for method in ['rule','reranker']:
            value=raw[method]
            added.append(dict(study='SoK',task='catalogue',condition='refresh_competition',
                method=method,case=case['case'],stratum=case['family'],
                correct=value['action'] in case['correct'],valid=True,latency_s=value['elapsed_s'],
                action=value['action'],source=rel(path)+'#line='+str(line)+'&method='+method,
                recorded_at=None,resolved_model=method,provider=None,platform='as-recorded',
                nodes=None,field_error_rate=None,collection_phase=rel(path.parent)))
    assert len(added)==336 and len({(r['method'],r['case']) for r in added})==336
    assert Counter(r['method'] for r in added)==Counter({m:48 for m in MODELS+['rule','reranker']})
    # first_new in the source is a different heuristic from first current entry;
    # do not relabel it or impute its unmeasured elapsed time.
    ROWS.extend(added)
    CHECKS['two_incoming_catalogue_records_checked']+=len(added)

def load_edge():
    manifest=read(EDGE/'manifest.json');assert not manifest['errors']
    cases={}
    for p in sorted((EDGE/'hf/data/edgebench/v1').glob('**/test.jsonl')):
        if p.parts[-3]=='RQ1b':continue
        rr=lines(p);cases[p.parts[-3],p.parts[-2]]={r['case_id']:r for r in rr}
    for p in sorted((EDGE/'hf/runs/EXP-2026-001').glob('**/ledger.jsonl')):
        for i,r in enumerate(lines(p),1):
            if r['rq']=='RQ1b' or r.get('repeat',0)!=0:continue
            c=cases[r['rq'],r['condition']][r['case_id']]
            assert c['bundle_size']==1
            valid=r['valid'] and len(r.get('labels') or [])==1
            fc=[valid and r['labels'][0].get(f)==c['truth'][0].get(f) for f in c['fields']]
            assert all(fc)==r['em'] and r['correct']==dict(zip(c['fields'],fc))
            assert r['cases_sha256']==HASHES[rel(EDGE/'hf/data/edgebench/v1'/r['rq']/r['condition']/'test.jsonl')]
            raw=r.get('raw_response')
            if raw is not None and r.get('raw_response_sha256'):
                assert hashlib.sha256(raw.encode()).hexdigest()==r['raw_response_sha256']
            cid=c['meta'].get('derived_from',c['case_id'])
            if r['rq']=='RQ1a':
                original=cases['RQ1a','base'][cid]
                assert original['truth']==c['truth'] and original['fields']==c['fields']
            ROWS.append(dict(study='Edge',task=r['rq'],condition=r['condition'],method=r['model'],
                case=cid,stratum=c['meta'].get('wording_family','all'),correct=bool(r['em']),valid=r['valid'],
                latency_s=r.get('latency_s'),field_error_rate=1-sum(fc)/len(fc),
                service_correct=bool(r['correct']['service_type']),
                source=rel(p)+':'+str(i),recorded_at=r.get('t_send_wall'),resolved_model=r.get('resolved_model'),
                provider=r.get('provider'),platform=r['platform'],nodes=None,
                seen=c['meta'].get('seen'),unsupported=c['meta'].get('is_unsupported'),
                post_timeout_wait_s=r.get('post_timeout_wait_s')))
            CHECKS['edge_labels_and_input_hash_checked']+=1
    for f in manifest['files']:
        p=EDGE/f['path']
        if rel(p) in HASHES:assert HASHES[rel(p)]==f['sha256']
    CHECKS['download_manifest_files']=len(manifest['files'])

def load_6g():
    primary, sources=c1_primary(SIXG)
    for p in sources:HASHES[rel(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for r in primary:
        c=r['_case']; ok=bool(r['valid']) and r['error_type'] is None
        ROWS.append(dict(study='6G',task='C1',condition=r['condition'],method=r['model'].split('@')[0],
          case=r['case_id'],stratum=c['meta']['wording_family'],correct=bool(ok and r['em']),valid=ok,
          target_cluster_correct=bool(ok and r['correct']['target_cluster']),half=c['half'],
          latency_s=r.get('latency_s'),field_error_rate=1-sum(r['correct'].values())/len(r['correct']),
          source=rel(Path(r['_source_path']))+':'+str(r['_line']),recorded_at=r.get('t_send_wall'),
          resolved_model=r.get('resolved_model'),provider=r.get('provider'),platform=r['platform'],
          collection_phase=r['_block'],nodes=None,post_timeout_wait_s=r.get('post_timeout_wait_s')))
    CHECKS['six_g_primary_records_checked']=len(primary)

def paired(left,right,label,rq):
    l={r['case']:r for r in left};r={x['case']:x for x in right}
    assert len(l)==len(left) and len(r)==len(right) and set(l)==set(r),(label,'unpaired cases')
    ids=sorted(l);q=np.array([int(l[c]['correct'])-int(r[c]['correct']) for c in ids])
    strata=defaultdict(list)
    for i,c in enumerate(ids):
        assert l[c]['stratum']==r[c]['stratum'];strata[l[c]['stratum']].append(i)
    rng=np.random.default_rng(42)
    ix=np.concatenate([rng.choice(s,(10000,len(s))) for _,s in sorted(strata.items())],axis=1)
    better=int(sum(q==1));worse=int(sum(q==-1));n=len(ids)
    answer=dict(rq=rq,study=left[0]['study'],task=left[0]['task'],method=left[0]['method'],
                contrast=label,left=left[0]['condition'],right=right[0]['condition'],n=n,
                delta_pp=float(q.mean()*100),ci95_pp=(np.quantile(q[ix].mean(axis=1),[.025,.975])*100).tolist(),
                improved=better,worsened=worse,strata=len(strata),paired_case_ids=ids,
                p_exact=binomtest(better,better+worse,.5).pvalue if better+worse else 1.0)
    if all(l[c]['latency_s'] is not None and r[c]['latency_s'] is not None for c in ids):
        t=np.array([l[c]['latency_s']-r[c]['latency_s'] for c in ids])
        answer.update(paired_median_latency_delta_s=float(np.median(t)),
                      latency_ci95_s=np.quantile(np.median(t[ix],axis=1),[.025,.975]).tolist())
    return answer

def build_contrasts():
    definitions={
      ('SoK','policy'): [('RQ-A',x,'base') for x in ['padded','repeated','effective16','effective64']],
      ('SoK','service'): [('RQ-B',x,'complete') for x in ['prose','missing','stale','conflict','resolved']]
          + [('RQ-E','public-'+x,x) for x in ['independent','complete','disjoint']]
          + [('RQ-E','public-complete','public-independent'),('RQ-E','complete','independent')],
      ('SoK','catalogue'): [('RQ-C',x,'base') for x in ['rekey','refresh','refresh_competition','absent']],
      ('SoK','route'): [('RQ-C','absent','present')],
      ('Edge','RQ1a'): [('RQ-A',x,'base') for x in ['pad_512','pad_2048','pad_8192','pad_16384']],
    }
    groups=defaultdict(list)
    for r in ROWS:groups[r['study'],r['task'],r['method'],r['condition']].append(r)
    out=[]
    for (study,task),specs in definitions.items():
        methods=sorted({r['method'] for r in ROWS if r['study']==study and r['task']==task})
        for m in methods:
            for rq,l,r in specs:
                if (study,task,m,l)==('SoK','catalogue','first','refresh_competition'):
                    continue
                a,b=groups[study,task,m,l],groups[study,task,m,r]
                assert a and b,(study,task,m,l,r)
                out.append(paired(a,b,l+' minus '+r,rq))
    sixg_methods=sorted({r['method'] for r in ROWS if r['study']=='6G'})
    for m in sixg_methods:
        # The telemetry-dependent half is the target-cluster endpoint used by H3.
        # The named-scope half and complete-policy endpoint remain in the big table.
        for rq,l,r in [('RQ-A',f'c{n}_fresh','c3_fresh') for n in [7,21,57]] + [
                ('RQ-B',f'c57_{q}','c57_fresh') for q in ['stale','noisy','contradictory']]:
            a,b=[[{**x,'correct':x['target_cluster_correct']} for x in groups['6G','C1',m,c]
                  if x['half']=='state_dependent'] for c in [l,r]]
            assert len(a)==len(b)==150
            result=paired(a,b,l+' minus '+r,rq)
            result['metric']='target_cluster_state_dependent'
            out.append(result)
    for rq in sorted({r['rq'] for r in out}):
        family=sorted([r for r in out if r['rq']==rq],key=lambda r:r['p_exact']);previous=0
        for i,r in enumerate(family):
            previous=max(previous,min(1,r['p_exact']*(len(family)-i)));r['p_holm']=previous
            r['holm_family_size']=len(family)
            r['outside_3pp_reference']=r['ci95_pp'][0]>3 or r['ci95_pp'][1]<-3
    return out

def online_views():
    result=[]
    for name,folder in [('policy','rq1-scale-20260923'),('service','service-scale-20260923'),('route','route-holdout-01')]:
        data=read(ROOT/'artifacts/sok'/folder/'online-source.json');groups=defaultdict(list)
        for r in data:
            raw=read(ROOT/r['source'])
            assert r['first_correct']==raw['first_correct'] and r['total_s']==raw['total_s']
            if name=='policy':direct=raw['direct']['success'];final=raw['final_verdict']['success']
            else:direct=raw['outcome']['success'];final=raw['final']['success']
            assert r['direct']==direct and r['final']==final
            groups[r['condition'],r['method']].append(r);CHECKS['sok_online_records_checked']+=1
        for (co,m),rs in sorted(groups.items()):
            result.append(dict(study='SoK',task=name,condition=co,method=m,n=len(rs),
              first_correct=sum(x['first_correct'] for x in rs),direct=sum(x['direct'] for x in rs),
              final=sum(x['final'] for x in rs),fallback=sum(x['fallback'] for x in rs),
              terminal_p50_s=float(np.median([x['total_s'] for x in rs])),
              terminal_p95_s=float(np.quantile([x['total_s'] for x in rs],.95)),
              inference='descriptive online subset; final includes fallback',source_ids=[x['source'] for x in rs]))
    for p in sorted((EDGE/'hf/runs/EXP-2026-002/rq5a').glob('load_*/seed_1/*/outcomes.jsonl')):
        rs=sorted(lines(p),key=lambda x:x['id']);assert len(rs)==300 and len({x['id'] for x in rs})==300
        assert all(rs[i]['arrival']<=rs[i+1]['arrival'] for i in range(299))
        flags=np.array([x['status']=='success' for x in rs]);blocks=flags.reshape(10,30).sum(axis=1)
        rng=np.random.default_rng(42);idx=rng.integers(0,10,(10000,10));boot=blocks[idx].sum(axis=1)/300
        decisions=[x['decision_elapsed_s'] for x in rs if x.get('decision_elapsed_s') is not None]
        queue=[x['queue_wait_s'] for x in rs if x.get('queue_wait_s') is not None]
        sup=[x for x in rs if x['truth']['service_type']!='unsupported']
        assert len(sup)==300
        for x in rs:
            if x['status']=='success':
                assert x['terminal']<=x['deadline'] and x['predicted']==x['truth']
            if x.get('decision_start') is not None and x.get('decision_end') is not None:
                assert x['decision_end']>=x['decision_start']>=x['arrival']-1e-6
        result.append(dict(study='Edge',task='RQ5a',condition=p.parts[-4],method=p.parts[-2],n=300,
             correct_on_time=int(sum(flags)),correct_on_time_rate=float(flags.mean()),
             correct_on_time_ci95=np.quantile(boot,[.025,.975]).tolist(),
             block_method='30 consecutive arrivals per block; whole-block bootstrap; seed42,10000 draws',
             offered_load=float(p.parts[-4].split('_')[1]),decision_observed_n=len(decisions),
             decision_p50_s=float(np.median(decisions)) if decisions else None,
             queue_observed_n=len(queue),queue_p50_s=float(np.median(queue)) if queue else None,
             queue_p95_s=float(np.quantile(queue,.95)) if queue else None,status_counts=dict(Counter(x['status'] for x in rs)),
             inference='measured live decisions + modeled service; no provider reliability inference',source_ids=[rel(p)]))
        CHECKS['edge_online_records_checked']+=300
    for item in rq3_primary(SIXG):
        rs=item['trace'];p=item['path'];pub=item['published'];integrity=item['integrity']
        HASHES[rel(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        ip=p.with_name('integrity.json');HASHES[rel(ip)]=hashlib.sha256(ip.read_bytes()).hexdigest()
        wait=[r['queue_wait_s'] for r in rs];services=[r['service_latency_s'] for r in rs]
        arrival=[r['arrival_s'] for r in rs]
        assert all(services[i]>=0 and wait[i]>=0 for i in range(len(rs)))
        result.append(dict(study='6G',task='RQ3',condition='rate_'+pub['rate_per_s'],method=pub['model'],n=300,
            offered_load=float(pub['rate_per_s']),observed_arrival_rate=(len(rs)-1)/(max(arrival)-min(arrival)),
            decision_slots=integrity['slots'],rho=float(pub['rate_per_s'])*float(np.mean(services))/integrity['slots'],
            published_rho=float(pub['rho']),queue_p50_s=float(np.median(wait)),queue_p95_s=float(np.quantile(wait,.95)),
            decision_p50_s=float(np.median(services)),decision_p95_s=float(np.quantile(services,.95)),
            share_enforced_within_1s=float(pub['share_enforced_within_1s']),
            completion_rate=sum(r.get('completion_s') is not None for r in rs)/len(rs),
            inference='Live interpretation plus documented A1/E2 schedule; not measured radio completion',
            source_ids=[rel(p),rel(ip)],collection_phase=p.parent.relative_to(SIXG/'hf/runs/rq3-load-traces').as_posix()))
        assert abs(result[-1]['rho']-float(pub['rho']))<1e-9
        CHECKS['six_g_online_primary_records_checked']+=300
    return result

def render_tables(cells,contrasts,online):
    lines=['# 跨研究综合：复算表','',
      '包括Edge、6G与SoK的逐条记录；各研究未合并。6G按公开主批次选择，全部额外尝试仍在原始来源中。口径见[分析记录](../../../docs/sok/cross-study-synthesis.md)。', '',
      '## 原生条件统计','', '|研究/任务|条件|方法/部署|正确/n|正确率95% Wilson区间|合法/n|p50 / p95 秒|', '|---|---|---|---:|---|---:|---|']
    for r in cells:
        ci=r['accuracy_ci95'];time='—' if r['p50_s'] is None else f"{r['p50_s']:.4f} / {r['p95_s']:.4f}"
        lines.append(f"|{r['study']}/{r['task']}|{r['condition']}|{r['method']} ({r['platform']})|{r['correct']}/{r['n']}|{ci[0]*100:.1f}–{ci[1]*100:.1f}%|{r['valid']}/{r['n']}|{time}|")
    lines+=['','## 6G遥测：目标簇正确率（状态依赖与命名范围分别保留）','',
      '|条件|解释器|子集|目标簇正确/n|95% Wilson区间|','|---|---|---|---:|---|']
    for r in cells:
        for subset,v in r.get('target_cluster_subsets',{}).items():
            ci=v['accuracy_ci95'];lines.append(f"|{r['condition']}|{r['method']}|{subset}|{v['correct']}/{v['n']}|{100*ci[0]:.1f}–{100*ci[1]:.1f}%|")
    lines+=['','## Edge目录：服务top-1分层（与四字段精确匹配分开）','','|条件|方法|子集|服务正确/n|95% Wilson区间|','|---|---|---|---:|---|']
    for r in cells:
        for subset,s in r.get('service_top1_subsets',{}).items():
            ci=s['accuracy_ci95'];lines.append(f"|{r['condition']}|{r['method']}|{subset}|{s['correct']}/{s['n']}|{100*ci[0]:.1f}–{100*ci[1]:.1f}%|")
    lines+=['','## 合法的研究内条件配对','',
      '差值为前一条件减后一条件；时延列为逐对差值的中位数。Edge字段数及目录条件没有可靠的实例配对，不进入此表。Holm只作用于本表RQ内正确率对比，区间仍为逐项区间。','',
      '|RQ/研究/任务及指标|方法|条件对比|n|正确率差pp [95%区间]|Holm p|配对时延差秒 [95%区间]|', '|---|---|---|---:|---|---:|---|']
    for r in contrasts:
        ci=r['ci95_pp'];tc=r.get('latency_ci95_s');time='—' if tc is None else f"{r['paired_median_latency_delta_s']:.4f} [{tc[0]:.4f}, {tc[1]:.4f}]"
        metric=r.get('metric','task_semantic_correctness')
        lines.append(f"|{r['rq']}/{r['study']}/{r['task']}/{metric}|{r['method']}|{r['contrast']}|{r['n']}|{r['delta_pp']:.1f} [{ci[0]:.1f}, {ci[1]:.1f}]|{r['p_holm']:.4g}|{time}|")
    lines+=['','## RQ-A：字段错误与控制预算（完整单元）','',
      '|研究/任务/条件|方法|字段平均错误率|合法返回≤100ms|合法返回≤1s|','|---|---|---:|---:|---:|']
    for r in cells:
        if (r['study'],r['task']) in [('Edge','RQ1a'),('Edge','RQ3'),('6G','C1'),('SoK','policy')]:
            fe=r.get('mean_field_error_rate');bp=r['validated_return_budget_probability']
            lines.append(f"|{r['study']}/{r['task']}/{r['condition']}|{r['method']}|{('—' if fe is None else f'{100*fe:.2f}%')}|{100*bp['0.1']:.1f}%|{100*bp['1.0']:.1f}%|")
    lines+=['','## RQ-E：节点数与门控方式完整表','','|条件|方法|3 workers|5 workers|8 workers|总正确率95%区间|合法/n|p50/p95秒|','|---|---|---:|---:|---:|---|---:|---|']
    for r in cells:
        if r['study']=='SoK' and r['task']=='service' and r['condition'] in ['independent','complete','disjoint','public-independent','public-complete','public-disjoint']:
            ns=r['by_nodes'];cs=[f"{ns[str(n)]['correct']}/{ns[str(n)]['n']}" for n in [3,5,8]];ci=r['accuracy_ci95']
            lines.append(f"|{r['condition']}|{r['method']}|{'|'.join(cs)}|{100*ci[0]:.1f}–{100*ci[1]:.1f}%|{r['valid']}/{r['n']}|{r['p50_s']:.4f}/{r['p95_s']:.4f}|")
    lines+=['','## SoK在线子集（描述性）','','|任务/条件|方法|n|首决策正确|直接完成|含兜底终态|兜底|终态p50/p95秒|','|---|---|---:|---:|---:|---:|---:|---|']
    for r in online:
        if r['study']=='SoK':lines.append(f"|{r['task']}/{r['condition']}|{r['method']}|{r['n']}|{r['first_correct']}|{r['direct']}|{r['final']}|{r['fallback']}|{r['terminal_p50_s']:.3f}/{r['terminal_p95_s']:.3f}|")
    lines+=['','## Edge负载轨迹','','|到达率/s|方法|准时正确/n|95%整段重抽样区间|排队p95秒|','|---:|---|---:|---|---:|']
    for r in online:
        if r['study']=='Edge':
            ci=r['correct_on_time_ci95'];q=r['queue_p95_s']
            lines.append(f"|{r['offered_load']}|{r['method']}|{r['correct_on_time']}/{r['n']}|{100*ci[0]:.1f}–{100*ci[1]:.1f}%|{q if q is not None else '—'}|")
    lines+=['','## 6G负载轨迹','',
      '|到达率/s|解释器|决策槽|ρ|排队p50/p95秒|1s内调度生效比例|','|---:|---|---:|---:|---|---:|']
    for r in online:
        if r['study']=='6G':lines.append(f"|{r['offered_load']}|{r['method']}|{r['decision_slots']}|{r['rho']:.4f}|{r['queue_p50_s']:.4f}/{r['queue_p95_s']:.4f}|{r['share_enforced_within_1s']:.4f}|")
    (OUT/'tables.md').write_text('\n'.join(lines)+'\n')

def render_rqe(contrasts):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Times New Roman','font.size':8,'axes.titlesize':8,
                         'axes.labelsize':8,'xtick.labelsize':7,'ytick.labelsize':8,
                         'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    methods=['jev','deepseek','gemini','glm47','qwen','rule','per_stage','ungated','first']
    names=['Jev','DeepSeek','Gemini','GLM','Qwen','Full rule','Per-stage rule','Ungated rule','First entry']
    specs=[('public-independent','independent','(a) Independent quota'),
           ('public-complete','complete','(b) Shared quota'),
           ('public-disjoint','disjoint','(c) Quota + separation'),
           ('public-complete','public-independent','(d) Shared − independent')]
    fig,axes=plt.subplots(1,4,figsize=(7.16,3.3),sharey=True)
    fig.subplots_adjust(left=.137,right=.99,top=.84,bottom=.22,wspace=.15)
    ys=np.arange(len(methods));colors=['#B9C6E0']*5+['#F4CC79']*4
    for ax,(left,right,title) in zip(axes,specs):
        rs=[next(c for c in contrasts if c['study']=='SoK' and c['task']=='service' and
                 c['method']==m and c['left']==left and c['right']==right) for m in methods]
        y=np.array([r['delta_pp'] for r in rs]);lo=y-np.array([r['ci95_pp'][0] for r in rs]);hi=np.array([r['ci95_pp'][1] for r in rs])-y
        bars=ax.barh(ys,y,height=.62,color=colors,edgecolor='#333333',linewidth=.45,zorder=3)
        for b,m in zip(bars,methods):
            if m not in MODELS:b.set_hatch('///')
        ax.errorbar(y,ys,xerr=np.array([lo,hi]),fmt='none',ecolor='#252525',elinewidth=.6,capsize=1.4,zorder=4)
        ax.axvline(0,color='#555555',linewidth=.7);ax.set_xlim(-75,75);ax.set_xticks([-50,0,50])
        ax.grid(axis='x',color='#dddddd',linewidth=.45,zorder=0);ax.set_title(title,pad=8)
        ax.set_yticks(ys,names);ax.tick_params(axis='y',length=0)
    axes[0].invert_yaxis()
    fig.text(.565,.135,'Paired accuracy difference (percentage points)',ha='center',fontsize=8)
    fig.text(.5,.965,'(a–c) Public gate − model self-check; (d) both conditions use the public gate',ha='center',fontsize=8)
    fig.text(.5,.048,'120 paired instances; 95% stratified bootstrap intervals. Workflow changes accompany gating.',ha='center',fontsize=7.5)
    for ext in ['pdf','svg','png']:fig.savefig(OUT/f'rq-e-gates.{ext}',dpi=220)
    plt.close(fig)

def render_rqc(cells):
    import matplotlib.pyplot as plt
    lookup={(r['study'],r['task'],r['condition'],r['method']):r for r in cells}
    edge_methods=['Jev-1.13.0','DeepSeek-V4.1-Flash','GLM-5.3-Flash','Qwen3.8-Flash',
                  'SemIf-Qwen3.5-4B@cuda','Laya@cuda','Qwen3.5-4B-JSON@cuda',
                  'DistilBERT-Clf-Frozen','DistilBERT-Clf-Retrained','MiniLM-Reranker']
    edge_names=['Jev','DeepSeek','GLM 5.3','Qwen 3.8','SemIf','Laya','Qwen JSON','DistilBERT F','DistilBERT R','MiniLM']
    names={'jev':'Jev','deepseek':'DeepSeek','gemini':'Gemini','glm47':'GLM 4.7','qwen':'Qwen 3.5',
           'rule':'Full rule','reranker':'MiniLM','first':'First entry','connectivity':'Link-only'}
    fig,axes=plt.subplots(1,4,figsize=(7.16,3.7))
    fig.subplots_adjust(left=.092,right=.995,bottom=.17,top=.76,wspace=.85)
    colors=['#B9C6E0','#F4CC79','#ED8683'];hatches=['','///','...']
    def panel(ax,title,labels,series,series_names):
        y=np.arange(len(labels));w=.72/len(series)
        for j,(rs,label) in enumerate(zip(series,series_names)):
            v=np.array([r['accuracy'] for r in rs])*100
            lo=v-np.array([r['accuracy_ci95'][0] for r in rs])*100
            hi=np.array([r['accuracy_ci95'][1] for r in rs])*100-v
            assert min(lo)>-1e-10 and min(hi)>-1e-10
            lo=np.maximum(lo,0);hi=np.maximum(hi,0)
            yy=y+(j-(len(series)-1)/2)*w
            ax.barh(yy,v,w,color=colors[j],edgecolor='#333333',linewidth=.35,hatch=hatches[j],label=label,zorder=3)
            ax.errorbar(v,yy,xerr=np.array([lo,hi]),fmt='none',ecolor='#333333',capsize=.7,elinewidth=.45,zorder=4)
        ax.set_yticks(y,labels,fontsize=6.6);ax.invert_yaxis();ax.set_xlim(0,105);ax.set_xticks([0,50,100])
        ax.tick_params(axis='y',length=0,pad=2);ax.grid(axis='x',color='#dddddd',linewidth=.4,zorder=0)
        ax.set_title(title,fontsize=7.4,pad=39)
        ax.legend(loc='lower center',bbox_to_anchor=(.5,1.005),frameon=False,fontsize=6.4,handlelength=1.25,labelspacing=.1,borderaxespad=0)
    panel(axes[0],'(a) Edge: 50% churn',edge_names,
          [[lookup['Edge','RQ4','churn50',m]['service_top1_subsets'][s] for m in edge_methods] for s in ['seen_supported','unseen_supported']],['Seen (n=136)','Unseen (n=134)'])
    mm=MODELS+['rule','reranker']
    panel(axes[1],'(b) SoK: catalog changes',['Lexical rule' if m=='rule' else names[m] for m in mm],
          [[lookup['SoK','catalogue',s,m] for m in mm] for s in ['base','rekey','refresh_competition']],['Stable','Renamed','Two incoming'])
    mm=MODELS+['rule','connectivity','first']
    panel(axes[2],'(c) SoK: route coverage',[names[m] for m in mm],
          [[lookup['SoK','route',s,m] for m in mm] for s in ['present','absent']],['Select: present','Escalate: absent'])
    mm=MODELS+['rule']
    panel(axes[3],'(d) SoK: escalation',['Task rules' if m=='rule' else names[m] for m in mm],
          [[lookup['SoK',task,'absent',m] for m in mm] for task in ['catalogue','route']],['Contract (n=48)','Route (n=120)'])
    fig.text(.55,.083,'Correct selection or escalation (%)',ha='center',fontsize=8)
    fig.text(.55,.025,'95% Wilson intervals; native tasks, model versions and denominators are retained.',ha='center',fontsize=7)
    for ext in ['pdf','svg','png']:fig.savefig(OUT/f'rq-c-coverage.{ext}',dpi=220)
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    load_sok();print('SoK fixed records',len(ROWS),flush=True)
    load_edge();load_6g();print('All fixed records',len(ROWS),flush=True)
    groups=defaultdict(list)
    for r in ROWS:groups[r['study'],r['task'],r['condition'],r['method'],r['platform']].append(r)
    cells=[]
    for (study,task,condition,method,platform),rs in sorted(groups.items()):
        assert len({r['case'] for r in rs})==len(rs),(study,task,condition,method)
        assert all(r['latency_s'] is None or (math.isfinite(r['latency_s']) and r['latency_s']>=0) for r in rs)
        result=dict(study=study,task=task,condition=condition,method=method,platform=platform,**summarize(rs))
        if study=='Edge':
            assert len(rs)==300
            result['mean_field_error_rate']=float(np.mean([r['field_error_rate'] for r in rs]))
            if task=='RQ4':
                subsets=[
                    ('seen_supported',[r for r in rs if r['seen'] and not r['unsupported']]),
                    ('unseen_supported',[r for r in rs if r['seen'] is False and not r['unsupported']]),
                    ('unsupported',[r for r in rs if r['unsupported']])]
                result['subsets']={name:summarize(sub) for name,sub in subsets if sub}
                result['service_top1_subsets']={name:summarize([{**r,'correct':r['service_correct']} for r in sub]) for name,sub in subsets if sub}
        if study=='SoK' and task=='service':
            result['by_nodes']={str(n):summarize([r for r in rs if r['nodes']==n]) for n in [3,5,8]}
        if study=='6G':
            result['target_cluster_subsets']={half:summarize([{**r,'correct':r['target_cluster_correct']}
                for r in rs if r['half']==half]) for half in ['state_dependent','named_scope']}
            result['mean_field_error_rate']=float(np.mean([r['field_error_rate'] for r in rs]))
        cells.append(result)
    # Independent arithmetic cross-check against preserved old summaries,
    # without executing or rewriting the old analysis programs.
    refs={name:read(ROOT/path) for name,path in {
        'policy':'experiments/EXP-019-effective-network-information/scale-seed42/analysis.json',
        'service':'experiments/EXP-020-service-chain-controls/scale-seed42/analysis.json',
        'route':'experiments/EXP-021-route-generalization/holdout-seed42/analysis.json'}.items()}
    for c in cells:
        if c['study']!='SoK' or c['task'] not in refs:continue
        matches=[r for r in refs[c['task']]['fixed'] if r['condition']==c['condition'] and r['method']==c['method']
                 and (c['task']!='policy' or r['task']=='policy')]
        assert len(matches)==1; old=matches[0]
        assert (c['n'],c['correct'],c['valid'])==(old['n'],old['correct'],old['valid'])
        assert abs(c['p50_s']-old['median_s'])<1e-9 and abs(c['p95_s']-old['p95_s'])<1e-9
        CHECKS['sok_cells_match_preserved_summary']+=1
    contrasts=build_contrasts();print('Paired contrasts',len(contrasts),flush=True)
    online=online_views()
    result=dict(status='CROSS_STUDY_CORE_RECOMPUTED_RQ_D_REQUIRES_E1',date='2026-10-03',seed=42,bootstrap_draws=10000,
      inference='Exploratory secondary analysis; no cross-study pooled estimate; fixed-input Wilson intervals, within-study paired stratified bootstrap, RQ-wise Holm for paired accuracy tests.',
      checks=dict(CHECKS),counts=dict(fixed_records=len(ROWS),cells=len(cells),paired_contrasts=len(contrasts),online_cells=len(online)),
      cells=cells,contrasts=contrasts,online=online,
      gaps=['Edge field-count and catalogue conditions are different cases: no arbitrary case-index pairing.',
            'P6 causal intervention belongs to E2, not run in this step.',
            'Complete RQ-D requires the subsequent E1 time-block and stability analysis.'])
    save(OUT/'results.json',result)
    with (OUT/'records.jsonl').open('w') as f:
        for r in ROWS:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n')
    for p in [Path(__file__),Path(__file__).with_name('sok_6g_analysis.py'),Path(__file__).with_name('sok_cross_study_figures.py')]:
        HASHES[rel(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    save(OUT/'source-manifest.json',dict(sources=HASHES,checks=dict(CHECKS),new_model_calls=0,
                                      six_g_raw_available=True,edge_release_manifest=rel(EDGE/'manifest.json'),
                                      six_g_release_manifest=rel(SIXG/'manifest.json')))
    render_tables(cells,contrasts,online)
    render_rqe(contrasts)
    render_rqc(cells)
    from sok_cross_study_figures import render_ab
    render_ab(result,OUT)
    print(json.dumps({'counts':result['counts'],'checks':CHECKS},indent=2),flush=True)

if __name__=='__main__':main()
