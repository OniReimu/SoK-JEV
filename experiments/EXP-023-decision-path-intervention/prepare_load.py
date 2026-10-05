"""Source-traced replay inputs: fixed empirical strata and D=0 physical residuals."""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import math
from analyze_sparse import check_rows, read_rows, terminal_observation

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def empirical_strata():
    e1_path = ROOT/'artifacts/sok/e1/results.json'
    records_path = ROOT/'artifacts/sok/cross-study/records.jsonl'
    e1 = json.loads(e1_path.read_text())
    assert e1['status'] == 'E1_REANALYSIS_COMPLETE'
    assert sha(records_path) == e1['source_records_sha256']
    groups = defaultdict(list)
    tasks = [('SoK', 'policy', 'base'), ('Edge', 'RQ1a', 'base'), ('6G', 'C1', 'c57_fresh')]
    for s in e1['fixed']:
        if (s['study'], s['task'], s['condition']) in tasks:
            groups[s['study'], s['method'], s['platform']].append(s)
    selected = [max(v, key=lambda s: (s['n'], s['collection_phase'])) for _, v in sorted(groups.items())]
    wanted = {src for s in selected for src in s['source_ids']}
    rows = {}
    with records_path.open() as f:
        for line in f:
            r = json.loads(line)
            if r['source'] in wanted:
                assert r['source'] not in rows
                rows[r['source']] = r
    assert set(rows) == wanted, 'Selected E1 timing source absent'
    result = []
    for i, s in enumerate(selected):
        times = []
        for src in s['source_ids']:
            row = rows[src]
            value = row.get('latency_s')
            assert value is not None and math.isfinite(value) and value >= 0, 'Unobserved timing cannot be imputed'
            times.append(dict(source=src, D_s=value))
        assert len(times) == s['n']
        result.append(dict(id='empirical-%02d' % i, type='empirical',
            identity={k:s[k] for k in ['study','task','condition','method','platform','collection_phase']},
            support=times, selection='All implementations/deployments in three declared baseline tasks; '
            'largest original stratum, lexical batch tie-break; no pooling across batches',
            timing_scope=s['selection_basis'],
            limitation='Resample observed client-return times; no model calls, semantic test, or provider concurrency claim'))
    return result, {str(e1_path.relative_to(ROOT)):sha(e1_path),
                    str(records_path.relative_to(ROOT)):sha(records_path)}


def read_empirical(path, expected_sha):
    assert expected_sha and sha(path) == expected_sha, 'Empirical input package changed'
    package = json.loads(path.read_text())
    assert package['status'] == 'E1_EMPIRICAL_DELAY_STRATA_FROZEN'
    empirical = package['empirical']
    assert len(empirical) == len({e['id'] for e in empirical}) == 24
    assert sum(len(e['support']) for e in empirical) == 5565
    for e in empirical:
        assert e['type'] == 'empirical'
        assert (e['identity']['study'], e['identity']['task'], e['identity']['condition']) in [
            ('SoK', 'policy', 'base'), ('Edge', 'RQ1a', 'base'), ('6G', 'C1', 'c57_fresh')]
        assert len(e['support']) == len({r['source'] for r in e['support']})
        assert all(math.isfinite(r['D_s']) and r['D_s'] >= 0 for r in e['support'])
    sources = dict(package['source_sha256'])
    sources[str(path.resolve())] = expected_sha
    return empirical, sources


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sparse', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--export-empirical', type=Path)
    p.add_argument('--empirical', type=Path)
    p.add_argument('--empirical-sha256')
    args = p.parse_args()
    if args.export_empirical:
        assert not any([args.sparse, args.out, args.empirical, args.empirical_sha256])
        empirical, sources = empirical_strata()
        package = dict(status='E1_EMPIRICAL_DELAY_STRATA_FROZEN', empirical=empirical,
                       source_sha256=sources,
                       purpose='Only observed timing supports for the already specified E2 load replay')
        assert not args.export_empirical.exists(), 'Do not overwrite a frozen replay package'
        args.export_empirical.parent.mkdir(parents=True, exist_ok=True)
        args.export_empirical.write_text(json.dumps(package, indent=2, allow_nan=False)+'\n')
        read_empirical(args.export_empirical, sha(args.export_empirical))
        print(json.dumps(dict(empirical_strata=len(empirical), support_values=sum(len(e['support']) for e in empirical),
                              sha256=sha(args.export_empirical), status=package['status'])))
        return
    assert args.sparse and args.out, '--sparse and --out are required for complete replay inputs'
    assert not args.out.exists(), 'Do not overwrite frozen load inputs'
    assert bool(args.empirical) == bool(args.empirical_sha256)
    sparse = args.sparse.resolve()
    status = json.loads((sparse/'status.json').read_text())
    assert status['phase'] == 'sparse_execution_complete_analysis_pending'
    empirical, sources = (read_empirical(args.empirical, args.empirical_sha256)
                          if args.empirical else empirical_strata())
    frozen = sparse/'frozen-inputs'
    hashes = json.loads((sparse/'source-hashes.json').read_text())
    physical = {}
    for domain in ['edge','transport']:
        path = sparse/domain/'records.jsonl'
        rows = read_rows(path)
        scene_path = frozen/(domain+'-scenarios.json')
        assert sha(scene_path) == hashes[domain+'-scenarios.json']
        ids = [s['id'] for s in json.loads(scene_path.read_text())]
        check_rows(rows, domain, ids, 10)
        sources[str(path)] = sha(path)
        support = []
        for row in rows:
            if row['injected_delay_s'] != 0:
                continue
            support.append(dict(scenario=row['scenario'], repeat=row['repeat'], status=row['status'],
                acknowledgement_s=row['ta']-row['td'] if row.get('ta') is not None else None,
                verified_outcome_s=row['tb']-row['td'] if row.get('tb') is not None else None,
                observation=terminal_observation(row),
                source=str(path)+'#'+row['scenario']+':'+str(row['repeat'])+':D0'))
        assert len(support) == 300
        physical[domain] = support
    controlled = [dict(id='controlled-'+str(d), type='controlled', D_s=d) for d in [0., .1, .5, 2.]]
    result = dict(purpose='formal_load_replay', seed=42, slots_per_cell=1,
        baseline_D_s=.1, baseline_samples=200, baseline_rhos=[.5,.8,.95],
        warmup_s=60., block_width_s=10., measured_blocks=20,
        drain_limit_s=7200., empirical=empirical, controlled=controlled,
        physical=physical, source_sha256=sources,
        budgets_s={'edge':2.,'transport':10.},
        common_arrival_trace_across_delays=True,
        physical_sampling='Uniform empirical D0 scene/repeat records including failures; same draw across delay cells',
        execution_scope='Measured physical residuals added after a real decision queue; no simultaneous topology actions',
        interval_scope='Time-block resampling describes this finite arrival window; overloaded cells are nonstationary',
        baseline_rule='c=1; lambda=rho_reference / measured mean of 200 isolated 100ms slot occupations; '
                      'fixed lambda across every controlled/empirical delay cell')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(physical_records=600, empirical_strata=len(empirical),
                         queue_cells=3*(4+len(empirical)), status='INPUTS_FROZEN_NO_LOAD_EXECUTED')))


if __name__ == '__main__':
    main()
