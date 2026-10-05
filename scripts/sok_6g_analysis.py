"""Read released 6G records with the documented primary selection; no model calls."""
from collections import defaultdict
from pathlib import Path
import csv
import hashlib
import json


def jsonlines(path):
    return [json.loads(x) for x in Path(path).read_bytes().splitlines() if x.strip()]


def c1_primary(base):
    gh, hf = base / 'github', base / 'hf'
    corpus = gh / 'data/ranbench/ranintent-v1/RQ4'
    cases = {p.parent.name: {r['case_id']: r for r in jsonlines(p)} for p in corpus.glob('*/test.jsonl')}
    case_hashes={p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in corpus.glob('*/test.jsonl')}
    blocks = defaultdict(lambda: defaultdict(list))
    source_files = [base/'manifest.json', base/'intake-check.json'] + list(corpus.glob('*/test.jsonl'))
    fields = ['action','class','scope','target_cluster','priority','prb_share','edge_site','latency_target','duration']
    for p in sorted((hf/'runs/c1').rglob('ledger.jsonl')):
        source_files.append(p)
        block = p.parent.relative_to(hf/'runs/c1').as_posix()
        for line, raw in enumerate(jsonlines(p), 1):
            r = dict(raw, _source_path=str(p), _line=line, _block=block)
            model = r['model'].split('@')[0]
            case = cases[r['condition']][r['case_id']]
            pred = (r.get('labels') or [{}])[0]
            correct = {f: bool(r['valid']) and pred.get(f)==case['truth'][f] for f in fields}
            assert correct==r['correct'] and (bool(r['valid']) and all(correct.values()))==r['em']
            assert r['cases_sha256']==case_hashes[r['condition']]
            r['_case'] = case
            blocks[model,r['condition']][block].append(r)
    avail_path = gh/'experiments/c1-interpretation/results/availability.csv'
    source_files.append(avail_path)
    with avail_path.open() as handle:
        availability = list(csv.DictReader(handle))
    primary = []
    for a in availability:
        bs = blocks[a['model'],a['condition']]
        assert sum(map(len,bs.values()))==int(a['total_n'])
        if a['primary_rule']=='per_case':
            ordered=sorted(bs,key=lambda b:(0 if b.split('/')[0]=='c1_hosted' else 1,
                                            min(r['t_send_wall'] for r in bs[b]),b))
            chosen={}
            for b in ordered:
                for r in bs[b]:
                    cid=r['case_id']
                    if cid not in chosen or (chosen[cid]['http_status']!=200 and r['http_status']==200):
                        chosen[cid]=r
            rows=list(chosen.values())
        else:
            rows=bs[a['primary_block']]
        assert len(rows)==300 and {r['case_id'] for r in rows}==set(cases[a['condition']])
        primary.extend(rows)
    assert len(primary)==33600
    return primary, source_files


def rq3_primary(base):
    path=base/'github/experiments/c1-interpretation/results/rq3-load/rq3_load.csv'
    with path.open() as handle:
        published=list(csv.DictReader(handle))
    answer=[]
    for r in published:
        suffix=r['source_trace'].split('/traces/',1)[1]
        p=base/'hf/runs/rq3-load-traces'/suffix
        integrity=json.loads(p.with_name('integrity.json').read_text())
        trace=jsonlines(p)
        assert integrity['complete'] and len(trace)==300
        assert integrity['model']==r['model'] and float(integrity['rate_per_s'])==float(r['rate_per_s'])
        if r['model']=='AnyJev-L0':assert suffix.startswith('selfhosted-d12-idle/')
        answer.append(dict(published=r,trace=trace,integrity=integrity,path=p))
    assert len(answer)==28
    return answer
