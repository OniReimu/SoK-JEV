"""Run the frozen physical E2 protocol inside its private, scheduled Linux guest."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
K3D = ROOT / 'artifacts/sok/e2-tools/k3d'
CONFIG = BASE / 'readiness-20261002/kubeconfig.yaml'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['calibration', 'sparse'], required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(mode=a.mode, phase='setup', started_utc=datetime.now(timezone.utc).isoformat(),
                 backend='batch-cluster', scheduler='pbs', job_id=os.environ['JEV_E2_PBS_JOB'],
                 vm_vcpus=8, vm_memory_mib=6144, gpus=0,
                 k3s_server_memory='1536m', k3s_agent_memory='768m')

    def save():
        tmp = out / 'status.tmp'
        tmp.write_text(json.dumps(state, indent=2) + '\n')
        tmp.replace(out / 'status.json')

    def command(cmd, name, timeout=240):
        (out / (name + '-command.json')).write_text(json.dumps([str(x) for x in cmd]) + '\n')
        with (out / (name + '.log')).open('a') as f:
            subprocess.run([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)

    save()
    hashes = {n: digest(BASE / n) for n in ['edge_measure.py', 'transport_measure.py',
        'transport_setup.py', 'edge-scenarios.json', 'transport-scenarios.json',
        'image_service.py', 'Dockerfile', 'edge-service.json', 'run_sparse.py', 'guest_experiment.py']}
    (out / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    try:
        command([K3D, 'cluster', 'create', 'jev-e2-pilot', '--agents', '2',
            '--image', 'rancher/k3s:v1.35.5-k3s1', '--servers-memory', '1536m',
            '--agents-memory', '768m', '--api-port', '127.0.0.1:57120',
            '--kubeconfig-update-default=false', '--kubeconfig-switch-context=false',
            '--k3s-arg', '--disable=traefik@server:0', '--k3s-arg',
            '--disable=servicelb@server:0', '--timeout', '240s'], 'cluster-create', 300)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG.open('w') as f:
            subprocess.run([str(K3D), 'kubeconfig', 'get', 'jev-e2-pilot'], stdout=f,
                           check=True, timeout=30)
        CONFIG.chmod(0o600)
        kube = ['kubectl', '--kubeconfig', str(CONFIG)]
        command(kube + ['wait', '--for=condition=Ready', 'nodes', '--all', '--timeout=180s'],
                'node-readiness')
        command([K3D, 'image', 'import', 'jev-e2-image:probe', '--cluster', 'jev-e2-pilot'],
                'image-import', 300)
        command(kube + ['apply', '-f', BASE / 'edge-service.json'], 'service-deploy')
        command(kube + ['-n', 'jev-e2', 'rollout', 'status', 'deployment/image-service',
                        '--timeout=120s'], 'service-ready', 150)
        command([sys.executable, BASE / 'transport_setup.py', '--out', out / 'transport-setup'],
                'transport-deploy', 150)
        assert digest(BASE / 'transport-scenarios.json') == hashes['transport-scenarios.json']
        from transport_measure import Lab
        lab = Lab(out / 'transport-setup')
        until = time.monotonic() + 120
        while True:
            try:
                planes = lab.plane()
                break
            except (AssertionError, KeyError):
                if time.monotonic() >= until:
                    raise
                time.sleep(2)
        (out / 'control-planes.json').write_text(json.dumps(planes, indent=2) + '\n')
        names = ['k3d-jev-e2-pilot-server-0', 'k3d-jev-e2-pilot-agent-0',
                 'k3d-jev-e2-pilot-agent-1'] + [f'clab-jev-e2-ring-r{i}' for i in range(1, 9)]
        command(['docker', 'inspect', '--format',
                 '{{.Name}} {{.Image}} {{.HostConfig.Memory}}', *names], 'runtime-images')
        command(['docker', 'info', '--format',
                 '{{.ServerVersion}} {{.Architecture}} {{.NCPU}} {{.MemTotal}}'], 'runtime-platform')
        state['phase'] = a.mode + '_running'
        save()
        if a.mode == 'calibration':
            command([sys.executable, BASE / 'edge_measure.py', '--out', out / 'edge',
                     '--scenarios', 'E10,E11,E30', '--repeats', '1'], 'edge-worker', 1200)
            command([sys.executable, BASE / 'transport_measure.py', '--out', out / 'transport',
                     '--scenarios', 'T03,T30', '--repeats', '1'], 'transport-worker', 600)
            counts = {}
            for domain, expected in [('edge', 12), ('transport', 8)]:
                rows = [json.loads(x) for x in (out / domain / 'records.jsonl').read_text().splitlines()]
                assert len(rows) == expected
                assert len({(r['scenario'], r['repeat'], r['injected_delay_s']) for r in rows}) == expected
                for r in rows:
                    assert r['status'] == 'verified'
                    assert r['t0'] <= r['td'] <= r['ta'] <= r['tb']
                    assert abs(r['D_s'] - (r['td'] - r['t0'])) < 1e-8
                    if domain == 'edge':
                        assert not set(r['baseline_uids']) & {x['uid'] for x in r['verified_replicas']}
                    else:
                        assert r['baseline_barrier']['quiet_s'] == 6
                counts[domain] = expected
            check = dict(status='PASS_REMOTE_CALIBRATION', counts=counts, formal_measurements=0,
                         source_hashes=hashes, same_resource_limits_required=True)
            (out / 'calibration-check.json').write_text(json.dumps(check, indent=2) + '\n')
            state.update(phase='calibration_verified', counts=counts, formal_measurements=0)
        else:
            command([sys.executable, BASE / 'run_sparse.py', '--out', out / 'sparse'],
                    'sparse-worker', 9 * 3600 + 300)
            result = json.loads((out / 'sparse/status.json').read_text())
            assert result['phase'] == 'sparse_execution_complete_analysis_pending'
            state.update(phase='sparse_execution_complete_analysis_pending', formal_measurements=2400)
    except Exception as exc:
        state.update(phase='FAILED_OR_INCOMPLETE', error=repr(exc))
        raise
    finally:
        for cmd in [[K3D, 'cluster', 'stop', 'jev-e2-pilot'],
                    ['docker', 'stop', *[f'clab-jev-e2-ring-r{i}' for i in range(1, 9)]]]:
            try:
                command(cmd, 'cleanup', 120)
            except Exception as exc:
                state.setdefault('cleanup_errors', []).append(repr(exc))
        state['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == '__main__':
    main()
