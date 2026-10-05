"""One fixed migration, four delay arms, one repeat: exploratory measurement probe."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import subprocess
import time
import urllib.request
from PIL import Image

BASE=Path(__file__).resolve().parent
RUN=BASE/'readiness-20261002'
CONFIG=RUN/'kubeconfig.yaml'


def main():
    # API proxy and kubectl always use this project's dedicated kubeconfig.
    proxy=subprocess.Popen(['kubectl','--kubeconfig',str(CONFIG),'proxy','--port=0','--address=127.0.0.1'],
        stdout=(RUN/'api-proxy.log').open('w'),stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            text=(RUN/'api-proxy.log').read_text()
            if '127.0.0.1:' in text:break
            time.sleep(.05)
        else:raise RuntimeError('API proxy did not start')
        origin='http://'+text.strip().split()[-1]
        def call(path,data=None,method='GET'):
            headers={}
            if data is not None:
                headers['Content-Type']='application/strategic-merge-patch+json'
                data=json.dumps(data).encode()
            req=urllib.request.Request(origin+path,data=data,headers=headers,method=method)
            with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
        ns='/api/v1/namespaces/jev-e2/pods'
        dep='/apis/apps/v1/namespaces/jev-e2/deployments/image-service'
        def patch(node):return call(dep,{'spec':{'template':{'spec':{'nodeSelector':{'kubernetes.io/hostname':node}}}}},'PATCH')
        def ready(node,timeout=90):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                pods=call(ns+'?labelSelector=app%3Dimage-service')['items']
                for pod in pods:
                    if pod['metadata'].get('deletionTimestamp'):continue
                    if pod.get('spec',{}).get('nodeName')!=node:continue
                    if any(c['type']=='Ready' and c['status']=='True' for c in pod.get('status',{}).get('conditions',[])):
                        return pod['metadata']['name']
                time.sleep(.05)
            raise RuntimeError('No Ready pod on required node: '+node)
        fixture=BytesIO();Image.new('RGB',(128,128),(255,0,0)).save(fixture,format='PNG');raw=fixture.getvalue()
        (RUN/'probe-input.png').write_bytes(raw)
        def verify(pod,node):
            path=ns+'/'+pod+':8080/proxy/thumbnail'
            req=urllib.request.Request(origin+path,data=raw,headers={'Content-Type':'image/png'},method='POST')
            with urllib.request.urlopen(req,timeout=10) as r:
                body=r.read();actual_node=r.headers['X-Node']
            result=Image.open(BytesIO(body));assert result.size==(64,64) and result.mode=='L'
            assert result.tobytes()==bytes([76])*(64*64) and actual_node==node
            return hashlib.sha256(body).hexdigest()
        baseline='k3d-jev-e2-pilot-agent-0';target='k3d-jev-e2-pilot-agent-1'
        records=[]
        for delay in [0.,.1,.5,2.]:
            patch(baseline);verify(ready(baseline),baseline)
            t0=time.monotonic();time.sleep(delay);td=time.monotonic()
            ack=patch(target);ta=time.monotonic()
            pod=ready(target);ready_at=time.monotonic();digest=verify(pod,target);tb=time.monotonic()
            row=dict(domain='edge',scenario='fixed_image_service_migration_agent0_to_agent1',repeat=0,
                injected_delay_s=delay,t0=t0,td=td,ta=ta,pod_ready_observed=ready_at,tb=tb,
                D_s=td-t0,Ta_s=ta-t0,Tb_s=tb-t0,D_over_Ta=(td-t0)/(ta-t0),D_over_Tb=(td-t0)/(tb-t0),
                deployment_generation=ack['metadata']['generation'],pod=pod,node=target,
                verified_output_sha256=digest,status='verified',
                probe='host API proxy to exact new pod; includes readiness polling ≤50ms and API-proxy/client overhead')
            records.append(row)
            with (RUN/'edge-probe.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
            print(json.dumps(row),flush=True)
        patch(baseline);verify(ready(baseline),baseline)
        assert len(records)==4
    finally:
        proxy.terminate();proxy.wait(timeout=10)


if __name__=='__main__':main()
