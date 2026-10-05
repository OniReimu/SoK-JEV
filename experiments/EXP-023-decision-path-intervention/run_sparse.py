"""Bounded, sequential physical E2 batch. No paid calls or scheduler notifications."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=out/'frozen-inputs';frozen.mkdir()
    paths=[BASE/name for name in ['transport_measure.py','edge_measure.py','run_sparse.py',
           'transport-scenarios.json','edge-scenarios.json','experiment.md','image_service.py','Dockerfile','edge-service.json']]
    paths+=list((BASE/'transport-ring').glob('*.conf'))+list((BASE/'transport-ring').glob('*.yml'))
    paths+=[BASE/'transport-ring/daemons']+list((BASE/'image-inputs').glob('*.png'))
    hashes={}
    for path in paths:
        rel=path.relative_to(BASE);target=frozen/rel;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target);hashes[str(rel)]=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    state=dict(phase='starting',pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),
               expected_per_domain=1200,formal_matrix='30 scenarios x 4 delays x 10 physical repeats',
               seed=42,paid_calls=0,analysis_complete=False)
    def save():
        state['updated_utc']=datetime.now(timezone.utc).isoformat()
        temp=out/'status.tmp';temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(out/'status.json')
    save();deadline=time.monotonic()+9*3600
    k3d=ROOT/'artifacts/sok/e2-tools/k3d'
    def command(cmd,log,timeout):
        with (out/log).open('a') as f:
            return subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout,check=True)
    try:
        names=['clab-jev-e2-ring-r'+str(i) for i in range(1,9)]+[
               'k3d-jev-e2-pilot-server-0','k3d-jev-e2-pilot-agent-0','k3d-jev-e2-pilot-agent-1']
        command(['docker','inspect','--format','{{.Name}} {{.Image}} {{.HostConfig.Memory}}',*names],
                'runtime-image-identities.log',30)
        for domain in ['edge','transport']:
            for rel,digest in hashes.items():
                if rel=='experiment.md':continue  # Frozen plan is retained; live progress may be appended.
                if hashlib.sha256((BASE/rel).read_bytes()).hexdigest()!=digest:
                    raise RuntimeError('Frozen experiment source changed: '+rel)
            state['phase']=domain+'_sparse_running';save()
            command([sys.executable,str(BASE/(domain+'_measure.py')),'--out',str(out/domain)],
                    domain+'-worker.log',max(1,deadline-time.monotonic()))
            result=json.loads((out/domain/'summary.json').read_text());state[domain]=result;save()
            if not result['formal'] or not result['complete'] or result['records']!=1200:
                raise RuntimeError('Incomplete physical matrix: '+domain)
            # Keep verification failures in the matrix; they are not selectively rerun.
            if domain=='edge':command([str(k3d),'cluster','stop','jev-e2-pilot'],'runtime-cleanup.log',120)
        state['phase']='sparse_execution_complete_analysis_pending'
    except Exception as exc:
        state.update(phase='execution_failed_or_incomplete',error=repr(exc));raise
    finally:
        for cmd in [[str(k3d),'cluster','stop','jev-e2-pilot'],
                    ['docker','stop',*[f'clab-jev-e2-ring-r{i}' for i in range(1,9)]]]:
            try:command(cmd,'runtime-cleanup.log',120)
            except Exception as exc:state.setdefault('cleanup_errors',[]).append(repr(exc))
        state['finished_utc']=datetime.now(timezone.utc).isoformat();save()


if __name__=='__main__':main()
