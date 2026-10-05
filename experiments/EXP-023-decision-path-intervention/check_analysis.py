"""Synthetic fault checks only; these observations are never scientific evidence."""
from copy import deepcopy
import math
import numpy as np
from analyze_sparse import DELAYS, check_rows, domain_result, terminal_observation
from run_load import replay_outcome
from analyze_load import check_cell, weighted_quantiles


def run_checks():
    rows = []
    for sid in ['check-a', 'check-b']:
        for d in DELAYS:
            row = dict(domain='edge', scenario=sid, repeat=0, injected_delay_s=d,
                status='verified', t0=10., td=10.+d, ta=10.+d+.25, tb=10.+d+.75,
                D_s=d, Ta_s=d+.25, Tb_s=d+.75, baseline_uids=['old'],
                verified_replicas=[dict(uid='new', t_end=10.+d+.75)])
            if sid == 'check-a' and d in [0., .1]:
                row.update(status='verification_failed', terminal=40.+d,
                           error="TimeoutError('synthetic verification wait')", tb=None, Tb_s=None)
                if d == .1:
                    row.update(ta=None, Ta_s=None, error="TimeoutError('synthetic API wait')")
            rows.append(row)
    result = domain_result(rows, 'edge', ['check-a', 'check-b'], repeats=1)
    zero, short = result['cells'][:2]
    assert zero['budgets']['1.0']['Tb']['numerator'] == 1
    assert zero['budgets']['1.0']['Tb']['denominator'] == 2
    assert zero['Tb']['observed_n'] == 1 and zero['Ta']['observed_n'] == 2
    assert short['Tb']['observed_n'] == short['Ta']['observed_n'] == 1
    assert zero['incomplete_observations'][0]['observed_until_s'] == 30.
    assert zero['incomplete_observations'][0]['unreached_endpoints'] == ['Tb']
    assert short['incomplete_observations'][0]['unreached_endpoints'] == ['Ta', 'Tb']
    bad = deepcopy(rows)
    bad[0]['terminal'] = bad[0]['td'] - 1.
    try:
        check_rows(bad, 'edge', ['check-a', 'check-b'], 1)
    except AssertionError:
        pass
    else:
        raise AssertionError('Invalid terminal time was accepted')

    physical = dict(status=rows[0]['status'], acknowledgement_s=.25,
                    verified_outcome_s=None, observation=terminal_observation(rows[0]))
    replay = replay_outcome(physical, 0, 3.)
    assert replay['Ta_s'] == 3.25 and replay['Tb_s'] is None
    assert replay['observed_until_s'] == 33.
    assert replay['source_error'] == rows[0]['error']
    event = dict(id=0, scheduled_offset_s=0., physical_indices={'edge': 0, 'transport': 0})
    queue_row = dict(arrival_id=0, scheduled_offset_s=0., t0=100., tq=101., td=103.,
                     t_release=103.001, queue_s=1., D_s=2., slot_s=2.001,
                     requested_D_s=2., replay={'edge': replay, 'transport': replay})
    check_cell([queue_row], [event], [dict(id=0, t0=100.)], dict(type='controlled', D_s=2.),
               dict(physical={'edge': [physical], 'transport': [physical]}))
    try:
        check_cell([queue_row], [event], [], dict(type='controlled', D_s=2.),
                   dict(physical={'edge': [physical], 'transport': [physical]}))
    except AssertionError:
        pass
    else:
        raise AssertionError('Missing actual arrivals were accepted')

    values = np.array([.1, np.nan, .9, 1.1, 3.])
    blocks = np.array([0, 0, 1, 1, 2])
    weights = np.array([[1, 1, 1], [0, 3, 0], [2, 0, 1]])
    got = weighted_quantiles(values, blocks, weights)
    for i, w in enumerate(weights):
        explicit = [v for v, b in zip(values, blocks) if math.isfinite(v) for _ in range(w[b])]
        assert np.allclose(got[:, i], np.quantile(explicit, [.5, .95]))
    print('PASS: incomplete endpoints, retained waits, full denominators, replay, and block quantiles')


if __name__ == '__main__':
    run_checks()
