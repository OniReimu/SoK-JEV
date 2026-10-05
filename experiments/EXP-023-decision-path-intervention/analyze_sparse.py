"""Scene-paired E2 analysis. Incomplete matrices cannot become formal results."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import math
import numpy as np

DELAYS = [0., .1, .5, 2.]
BUDGETS = [.5, 1., 2., 5., 10.]
BOOT = 10000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def terminal_observation(row):
    """Retain time spent observing an incomplete action without inventing its endpoint."""
    stop = row['tb'] if row['status'] == 'verified' else row['terminal']
    assert math.isfinite(stop) and stop >= row['td']
    if row.get('ta') is not None:
        assert stop >= row['ta']
    return dict(observed_until_s=stop-row['t0'],
                postdecision_observed_until_s=stop-row['td'],
                unreached_endpoints=[name for name, key in [('Ta', 'ta'), ('Tb', 'tb')]
                                     if row.get(key) is None],
                error=row.get('error'))


def check_rows(rows, domain, scenarios, repeats):
    expected = {(s, r, d) for s in scenarios for r in range(repeats) for d in DELAYS}
    keys = [(r['scenario'], r['repeat'], r['injected_delay_s']) for r in rows]
    assert len(keys) == len(set(keys)), 'Duplicate physical measurement'
    assert set(keys) == expected, 'Incomplete or unexpected physical matrix'
    for r in rows:
        assert r['domain'] == domain and r['status'] in ['verified', 'verification_failed']
        assert r['td'] >= r['t0'] and r['D_s'] >= r['injected_delay_s'] - .001
        assert abs(r['D_s'] - (r['td'] - r['t0'])) < 1e-8
        if r.get('ta') is not None:
            assert r['ta'] >= r['td']
            assert abs(r['Ta_s'] - (r['ta'] - r['t0'])) < 1e-8
        if r['status'] == 'verified':
            assert r['tb'] >= r['ta']
            assert abs(r['Tb_s'] - (r['tb'] - r['t0'])) < 1e-8
            if domain == 'edge':
                assert not set(r['baseline_uids']) & {p['uid'] for p in r['verified_replicas']}
                assert abs(r['tb'] - max(p['t_end'] for p in r['verified_replicas'])) < 1e-8
            else:
                assert r['baseline_barrier']['end'] <= r['t0']
                assert r['baseline_barrier']['quiet_s'] == 6
                assert 'dev eth2' in r['route']
                assert max(r['rtt_ms']) <= r['rtt_verification_bound_ms']
        else:
            assert r.get('Tb_s') is None and r.get('tb') is None
            assert r.get('error'), 'Incomplete action must retain its original failure reason'
        terminal_observation(r)
    return dict(records=len(rows), status_counts=dict(Counter(r['status'] for r in rows)))


def finite_quantile(values, q):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    return float(np.quantile(a, q)) if len(a) else None


def ci(values):
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    return np.quantile(a, [.025, .975]).tolist() if len(a) else None


def matrix(rows, ids, field, delay, repeats):
    lookup = {(r['scenario'], r['repeat'], r['injected_delay_s']): r for r in rows}
    return np.asarray([[lookup[s, rep, delay].get(field)
                        if lookup[s, rep, delay].get(field) is not None else np.nan
                        for rep in range(repeats)] for s in ids], dtype=float)


def bootstrap_quantiles(a, samples, quantiles):
    draws = a[samples].reshape(len(samples), -1)
    live = np.isfinite(draws).any(axis=1)
    result = np.full((len(quantiles), len(samples)), np.nan)
    if live.any():
        result[:, live] = np.nanquantile(draws[live], quantiles, axis=1)
    return result


def describe(a, samples):
    """Whole-scene resampling retains all nested physical repeats."""
    flat = a.ravel()
    finite = np.isfinite(flat)
    if not finite.any():
        return dict(observed_n=0, p50_s=None, p95_s=None, ci95_p50_s=None, ci95_p95_s=None)
    boot = bootstrap_quantiles(a, samples, [.5, .95])
    return dict(observed_n=int(finite.sum()), p50_s=finite_quantile(flat, .5),
                p95_s=finite_quantile(flat, .95), ci95_p50_s=ci(boot[0]), ci95_p95_s=ci(boot[1]))


def probability(a, budget, samples):
    # Missing/unverified outcomes are deadline misses, never dropped from the denominator.
    flags = np.isfinite(a) & (a <= budget)
    return dict(numerator=int(flags.sum()), denominator=int(flags.size), value=float(flags.mean()),
                ci95=ci(flags[samples].mean(axis=(1, 2))))


def slopes(rows, ids, endpoint, repeats):
    scene = []
    excluded = []
    by_scene = {s: sorted([r for r in rows if r['scenario'] == s],
                         key=lambda r: (r['repeat'], r['injected_delay_s'])) for s in ids}
    for sid, rs in by_scene.items():
        if len(rs) != repeats * 4 or any(r.get(endpoint) is None for r in rs):
            excluded.append(sid)
            continue
        x = np.asarray([r['D_s'] for r in rs])
        y = np.asarray([r[endpoint] for r in rs])
        beta = float(np.sum((x-x.mean()) * (y-y.mean())) / np.sum((x-x.mean())**2))
        lookup = {(r['repeat'], r['injected_delay_s']): r for r in rs}
        delta = [lookup[i, 2.][endpoint] - lookup[i, 0.][endpoint] for i in range(repeats)]
        delta_d = [lookup[i, 2.]['D_s'] - lookup[i, 0.]['D_s'] for i in range(repeats)]
        relative_gain = [(lookup[i, 2.][endpoint] - lookup[i, 0.][endpoint]) /
                         lookup[i, 2.][endpoint] for i in range(repeats)]
        scene.append(dict(scenario=sid, slope=beta, paired_delta_s=float(np.mean(delta)),
                          paired_actual_D_delta_s=float(np.mean(delta_d)),
                          paired_relative_gain=float(np.mean(relative_gain))))
    result = dict(endpoint=endpoint, eligible_scenes=len(scene), excluded_scenes=excluded,
                  conditioning='All 40 endpoint observations in the scene are available', scenes=scene)
    if len(scene) < 2:
        return dict(result, inferential_status='unavailable', slope_mean=None, p_raw=None)
    arr = np.asarray([s['slope'] for s in scene])
    samples = np.random.default_rng(42).integers(0, len(scene), (BOOT, len(scene)))
    boot = arr[samples].mean(axis=1)
    mean = float(arr.mean())
    interval = ci(boot)
    # Centered scene bootstrap null; this is not an exact randomization test.
    p = (int(np.sum(np.abs(boot - mean) >= abs(mean - 1))) + 1) / (BOOT + 1)
    result.update(inferential_status='scene_cluster_bootstrap', slope_mean=mean, slope_ci95=interval,
                  practical_range=[.9, 1.1],
                  ci_within_practical_range=bool(interval[0] >= .9 and interval[1] <= 1.1),
                  ci_overlaps_practical_range=bool(interval[1] >= .9 and interval[0] <= 1.1),
                  p_raw=p, test='two-sided centered scene-bootstrap null of mean slope = 1')
    for name in ['paired_delta_s', 'paired_actual_D_delta_s', 'paired_relative_gain']:
        v = np.asarray([s[name] for s in scene])
        result[name] = dict(mean=float(v.mean()), ci95=ci(v[samples].mean(axis=1)))
    return result


def domain_result(rows, domain, ids, repeats=10):
    result = dict(domain=domain, check=check_rows(rows, domain, ids, repeats), cells=[])
    samples = np.random.default_rng(42).integers(0, len(ids), (BOOT, len(ids)))
    reference = 2. if domain == 'edge' else 10.
    for delay in DELAYS:
        d = matrix(rows, ids, 'D_s', delay, repeats)
        ta = matrix(rows, ids, 'Ta_s', delay, repeats)
        tb = matrix(rows, ids, 'Tb_s', delay, repeats)
        cell = dict(injected_delay_s=delay, n=len(ids)*repeats, reference_budget_s=reference,
                    rho=None, D=describe(d, samples), Ta=describe(ta, samples), Tb=describe(tb, samples),
                    endpoint_quantiles='Conditional on observed acknowledgement / verified outcome',
                    D_over_Ta_median=finite_quantile(d/ta, .5), D_over_Tb_median=finite_quantile(d/tb, .5),
                    D_over_Ta_ci95=ci(bootstrap_quantiles(d/ta, samples, [.5])[0]),
                    D_over_Tb_ci95=ci(bootstrap_quantiles(d/tb, samples, [.5])[0]),
                    budgets={str(b): dict(Ta=probability(ta, b, samples), Tb=probability(tb, b, samples))
                             for b in BUDGETS})
        cell['stage_medians_s'] = dict(decision=finite_quantile(d, .5),
            acknowledgement_after_decision=finite_quantile(ta-d, .5),
            verification_after_acknowledgement=finite_quantile(tb-ta, .5))
        cell['stage_stack_limit'] = 'Sum of stage medians; generally not the median total latency'
        failures = [dict(scenario=r['scenario'], repeat=r['repeat'], **terminal_observation(r))
                    for r in rows if r['injected_delay_s'] == delay and r['status'] != 'verified']
        cell['incomplete_observations'] = failures
        cell['completion_counts'] = dict(acknowledged=int(np.isfinite(ta).sum()),
            verified=int(np.isfinite(tb).sum()), unverified=len(failures), arrivals=int(tb.size))
        cell['incomplete_observation_limit'] = (
            'Failure/timeout observation durations are not completion times; no endpoint is imputed.')
        result['cells'].append(cell)
    result['slopes'] = [slopes(rows, ids, endpoint, repeats) for endpoint in ['Ta_s', 'Tb_s']]
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True, help='Directory written by run_sparse.py')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run = a.run.resolve()
    state = json.loads((run/'status.json').read_text())
    assert state['phase'] == 'sparse_execution_complete_analysis_pending', 'Formal batch is incomplete'
    frozen = run/'frozen-inputs'
    hashes = json.loads((run/'source-hashes.json').read_text())
    for rel, digest in hashes.items():
        assert sha(frozen/rel) == digest, 'Frozen input changed: ' + rel
    source = {str(run/'source-hashes.json'): sha(run/'source-hashes.json')}
    result = dict(status='E2_SPARSE_ANALYZED_LOAD_PENDING', seed=42, bootstrap_draws=BOOT,
        unit='30 scenes per domain; retain 10 nested physical repeats in whole-scene resampling',
        source_run=str(run), domains=[], limits=[
            'Exploratory design refined during separate calibration; not preregistered.',
            'Between-domain comparisons are descriptive; probes and actions differ.',
            'Endpoint quantiles condition on observed outcomes; all arrivals remain in budget denominators.',
            'Reference budgets are task targets, not production SLAs.',
            'No queue/load or long-run stability result is established by the sparse arm.'])
    for domain in ['edge', 'transport']:
        path = run/domain/'records.jsonl'
        source[str(path)] = sha(path)
        rows = read_rows(path)
        ids = [s['id'] for s in json.loads((frozen/(domain+'-scenarios.json')).read_text())]
        assert len(ids) == 30 and len(rows) == 1200
        manifest = json.loads((run/domain/'manifest.json').read_text())
        assert manifest['scenarios_sha256'] == hashes[domain+'-scenarios.json']
        assert sha(run/domain/'measurement-code.py') == hashes[domain+'_measure.py']
        if 'code_sha256' in manifest:
            assert manifest['code_sha256'] == hashes[domain+'_measure.py']
        result['domains'].append(domain_result(rows, domain, ids))
    tests = [s for d in result['domains'] for s in d['slopes'] if s.get('p_raw') is not None]
    previous = 0.
    for i, s in enumerate(sorted(tests, key=lambda s: s['p_raw'])):
        previous = max(previous, min(1., (4-i)*s['p_raw']))
        s['p_holm_family4'] = previous
    result['holm_family'] = 'Two domains x Ta/Tb mean-slope deviation from 1; family size 4'
    a.out.mkdir(parents=True, exist_ok=True)
    result['source_sha256'] = source
    result['analysis_code_sha256'] = sha(Path(__file__))
    (a.out/'sparse-results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'], records=2400, domains=2)))


if __name__ == '__main__':
    main()
