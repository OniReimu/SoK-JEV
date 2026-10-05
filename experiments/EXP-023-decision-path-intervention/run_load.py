"""Real FIFO decision queues, then traced empirical execution replay. No model calls."""
from pathlib import Path
import argparse
import asyncio
import hashlib
import json
import os
import random
import shutil
import socket
import time


def replay_outcome(physical, physical_index, decision_return_s):
    a = physical['acknowledgement_s']
    b = physical['verified_outcome_s']
    result = dict(physical_index=physical_index, source_status=physical['status'],
        Ta_s=decision_return_s+a if a is not None else None,
        Tb_s=decision_return_s+b if b is not None else None)
    if 'observation' in physical:
        observation = physical['observation']
        result.update(observed_until_s=decision_return_s+observation['postdecision_observed_until_s'],
                      unreached_endpoints=observation['unreached_endpoints'],
                      source_error=observation['error'])
    return result


async def execute(config, out):
    formal = config['purpose'] == 'formal_load_replay'
    assert config['slots_per_cell'] == 1
    if formal:
        assert config['baseline_D_s'] == .1 and config['baseline_samples'] == 200
        assert config['warmup_s'] == 60. and config['block_width_s'] == 10.
        assert config['measured_blocks'] == 20 and config['seed'] == 42
        assert [x['D_s'] for x in config['controlled']] == [0., .1, .5, 2.]
        assert config['baseline_rhos'] == [.5, .8, .95]
        assert all(len(config['physical'][d]) == 300 for d in ['edge', 'transport'])
        assert all('observation' in p for records in config['physical'].values() for p in records)
    state = dict(phase='baseline_calibration', purpose=config['purpose'], backend='batch-cluster',
                 scheduler='pbs', job_id=os.environ.get('PBS_JOBID'), host=socket.gethostname(),
                 gpus=0, paid_calls=0, slots_per_cell=1, cells={}, seed=config['seed'])

    def save():
        state['updated_unix'] = time.time()
        p = out/'status.tmp'
        p.write_text(json.dumps(state, indent=2, allow_nan=False)+'\n')
        p.replace(out/'status.json')

    save()
    baseline = []
    for _ in range(config['baseline_samples']):
        begin = time.monotonic()
        await asyncio.sleep(config['baseline_D_s'])
        end = time.monotonic()
        baseline.append(dict(t_start=begin, t_end=end, service_s=end-begin))
    mean = sum(r['service_s'] for r in baseline)/len(baseline)
    (out/'baseline.json').write_text(json.dumps(dict(samples=baseline, mean_slot_s=mean), indent=2)+'\n')
    rates = [rho/mean for rho in config['baseline_rhos']]
    conditions = config['controlled'] + config['empirical']
    rng = random.Random(config['seed'])
    horizon = config['warmup_s'] + config['block_width_s']*config['measured_blocks']
    traces = []
    for i, rate in enumerate(rates):
        trace = []
        offset = 0.
        while True:
            offset += rng.expovariate(rate)
            if offset >= horizon:
                break
            trace.append(dict(id=len(trace), scheduled_offset_s=offset, delay_uniform=rng.random(),
                physical_indices={d:rng.randrange(len(config['physical'][d])) for d in ['edge','transport']}))
        assert trace
        traces.append(trace)
    (out/'arrival-plan.json').write_text(json.dumps(dict(lambda_per_s=rates, traces=traces), indent=2)+'\n')
    state.update(phase='arrival_and_queue_running', baseline_mean_slot_s=mean,
                 lambda_per_s=rates, horizon_s=horizon, expected_per_rate=[len(t) for t in traces])
    queues = {}
    output_queue = asyncio.Queue()
    epoch = time.monotonic()+1.
    state['epoch_monotonic'] = epoch
    files = {}
    tasks = []

    async def writer():
        while True:
            item = await output_queue.get()
            if item is None:
                output_queue.task_done()
                return
            cell_id, row = item
            files[cell_id].write(json.dumps(row, separators=(',',':'), allow_nan=False)+'\n')
            output_queue.task_done()

    async def worker(cell_id, condition, q):
        while True:
            item = await q.get()
            if item is None:
                q.task_done()
                return
            arrival, t0 = item
            tq = time.monotonic()
            if condition['type'] == 'controlled':
                requested = condition['D_s']
                source_index = None
            else:
                source_index = min(int(arrival['delay_uniform']*len(condition['support'])), len(condition['support'])-1)
                requested = condition['support'][source_index]['D_s']
            # The FIFO worker is the decision slot. Sleep occurs before its release.
            await asyncio.sleep(requested)
            td = time.monotonic()
            replay = {}
            for domain in ['edge','transport']:
                physical_index = arrival['physical_indices'][domain]
                physical = config['physical'][domain][physical_index]
                replay[domain] = replay_outcome(physical, physical_index, td-t0)
            row = dict(arrival_id=arrival['id'], scheduled_offset_s=arrival['scheduled_offset_s'],
                t0=t0, tq=tq, td=td, requested_D_s=requested, empirical_source_index=source_index,
                queue_s=tq-t0, D_s=td-tq, replay=replay)
            row['t_release'] = time.monotonic()
            row['slot_s'] = row['t_release']-tq
            output_queue.put_nowait((cell_id,row))
            state['cells'][cell_id]['completed'] += 1
            q.task_done()

    arrivals_file = (out/'arrivals.jsonl').open('w', buffering=1)

    async def producer(i, trace):
        qlist = [queues['r'+str(i)+'-'+c['id']] for c in conditions]
        for event in trace:
            wait = epoch+event['scheduled_offset_s']-time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            t0 = time.monotonic()
            arrivals_file.write(json.dumps(dict(rate_index=i,id=event['id'],t0=t0,
                scheduled_offset_s=event['scheduled_offset_s'],
                arrival_lag_s=t0-epoch-event['scheduled_offset_s']))+'\n')
            # One observed arrival time and workload draw are shared across every D at this lambda.
            for q in qlist:
                q.put_nowait((event,t0))
        for q in qlist:
            q.put_nowait(None)

    async def progress():
        while True:
            await asyncio.sleep(30)
            for f in files.values():
                f.flush()
            save()

    for i, trace in enumerate(traces):
        for c in conditions:
            cell_id = 'r'+str(i)+'-'+c['id']
            q = asyncio.Queue()
            queues[cell_id] = q
            files[cell_id] = (out/(cell_id+'.jsonl')).open('w', buffering=1)
            state['cells'][cell_id] = dict(rate_index=i, condition_id=c['id'], lambda_per_s=rates[i],
                baseline_rho=config['baseline_rhos'][i], expected=len(trace), completed=0)
            tasks.append(asyncio.ensure_future(worker(cell_id,c,q)))
    log_task = asyncio.ensure_future(writer())
    progress_task = asyncio.ensure_future(progress())
    save()
    try:
        await asyncio.gather(*[producer(i,t) for i,t in enumerate(traces)])
        state['phase'] = 'draining_queued_arrivals'
        save()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=config['drain_limit_s'])
        await output_queue.join()
        for c in state['cells'].values():
            assert c['completed'] == c['expected']
        state['phase'] = 'LOAD_EXECUTION_COMPLETE_ANALYSIS_PENDING' if formal else 'DIAGNOSTIC_COMPLETE'
    except BaseException as exc:
        state.update(phase='INCOMPLETE', error=repr(exc))
        for task in tasks:
            task.cancel()
        raise
    finally:
        progress_task.cancel()
        output_queue.put_nowait(None)
        await log_task
        for f in files.values():
            f.close()
        arrivals_file.close()
        state['finished_unix'] = time.time()
        save()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    config = json.loads(args.inputs.read_text())
    args.out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.inputs,args.out/'inputs.json')
    shutil.copyfile(__file__,args.out/'measurement-code.py')
    (args.out/'manifest.json').write_text(json.dumps(dict(
        inputs_sha256=hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        platform=os.uname()._asdict() if hasattr(os.uname(),'_asdict') else list(os.uname()),
        interpretation='Real single-slot FIFO queues; conditional empirical execution replay; no live model inference'),indent=2)+'\n')
    loop = asyncio.get_event_loop()
    loop.run_until_complete(execute(config,args.out))


if __name__ == '__main__':
    main()
