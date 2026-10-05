"""Physical migration and replica expansion; two endpoints and complete baseline reset."""
from pathlib import Path
from io import BytesIO
import argparse
import hashlib
import json
import os
import random
import subprocess
import time
import urllib.request
from PIL import Image

BASE=Path(__file__).resolve().parent
CONFIG=BASE/'readiness-20261002/kubeconfig.yaml'
FRR=os.environ.get('JEV_E2_FRR_IMAGE','quay.io/frrouting/frr@sha256:54aca1fe272e8ab298aba491211d4b4a303ff95aa42cf7ff6487b14dc7b4e513')
NS='/api/v1/namespaces/jev-e2/pods'
DEP='/apis/apps/v1/namespaces/jev-e2/deployments/image-service'


class Edge:
    def __init__(self,out):self.out=out;self.proxy=None

    def start(self):
        self.proxy_log=(self.out/'api-proxy.log').open('w')
        self.proxy=subprocess.Popen(['kubectl','--kubeconfig',str(CONFIG),'proxy','--port=0','--address=127.0.0.1'],stdout=self.proxy_log,stderr=subprocess.STDOUT)
        for _ in range(100):
            text=(self.out/'api-proxy.log').read_text()
            if '127.0.0.1:' in text:
                self.origin='http://'+text.strip().split()[-1];break
            time.sleep(.05)
        else:raise RuntimeError('Project API proxy did not start')
        self.api(DEP,{'spec':{'template':{'spec':{'terminationGracePeriodSeconds':2}}}},'PATCH')

    def stop(self):
        if self.proxy is not None:self.proxy.terminate();self.proxy.wait(timeout=10);self.proxy_log.close()

    def api(self,path,data=None,method='GET'):
        headers={}
        if data is not None:data=json.dumps(data).encode();headers['Content-Type']='application/strategic-merge-patch+json'
        start=time.monotonic()
        req=urllib.request.Request(self.origin+path,data=data,headers=headers,method=method)
        with urllib.request.urlopen(req,timeout=20) as r:result=json.load(r)
        with (self.out/'api.jsonl').open('a') as f:
            f.write(json.dumps(dict(t_start=start,t_end=time.monotonic(),path=path,method=method))+'\n')
        return result

    def patch(self,node,n):
        return self.api(DEP,{'spec':{'replicas':n,'template':{'spec':{'nodeSelector':{'kubernetes.io/hostname':node}}}}},'PATCH')

    def pods(self):return self.api(NS+'?labelSelector=app%3Dimage-service')['items']

    def ready(self,node,n,clear_old=False,timeout=60):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            pods=self.pods()
            alive=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
            chosen=[p for p in alive if p['spec'].get('nodeName')==node and any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[]))]
            if len(chosen)==n and (not clear_old or len(pods)==len(alive)==n):return chosen
            time.sleep(.05)
        raise RuntimeError('Desired Ready replicas / complete baseline reset not reached')

    def verify(self,pod,fixture,node):
        raw=(BASE/fixture['image']).read_bytes();assert hashlib.sha256(raw).hexdigest()==fixture['input_sha256']
        path=NS+'/'+pod['metadata']['name']+':8080/proxy/thumbnail'
        start=time.monotonic();req=urllib.request.Request(self.origin+path,data=raw,headers={'Content-Type':'image/png'},method='POST')
        with urllib.request.urlopen(req,timeout=30) as r:body=r.read();actual=r.headers['X-Node']
        end=time.monotonic();image=Image.open(BytesIO(body))
        digest=hashlib.sha256(image.tobytes()).hexdigest()
        assert image.mode=='L' and image.size==(64,64) and digest==fixture['expected_gray_pixels_sha256'] and actual==node
        return dict(pod=pod['metadata']['name'],uid=pod['metadata']['uid'],node=actual,t_start=start,t_end=end,gray_pixels_sha256=digest)

    def netem(self,settings):
        for node,delay in settings.items():
            cmd=['docker','run','--rm','--cap-add','NET_ADMIN','--network','container:'+node,
                 '--entrypoint','/sbin/tc',FRR,'qdisc','replace','dev','eth0','root','netem','delay',str(delay)+'ms']
            start=time.monotonic();r=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
            with (self.out/'netem.jsonl').open('a') as f:f.write(json.dumps(dict(t_start=start,t_end=time.monotonic(),command=cmd,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))+'\n')
            if r.returncode:raise RuntimeError(r.stderr)

    def warm(self,fixture):
        # Same image and module caches on both workers before measured operations.
        for node in ['k3d-jev-e2-pilot-agent-0','k3d-jev-e2-pilot-agent-1']:
            self.patch(node,1);pods=self.ready(node,1,clear_old=True)
            self.verify(pods[0],fixture,node)

    def measure(self,s,delay,repeat,index):
        self.patch(s['baseline_node'],1)
        before=self.ready(s['baseline_node'],1,clear_old=True)
        self.verify(before[0],s['fixture'],s['baseline_node'])
        old={p['metadata']['uid'] for p in before}
        row=dict(domain='edge',scenario=s['id'],kind=s['kind'],repeat=repeat,order=index,
                 injected_delay_s=delay,baseline_uids=sorted(old),status='pending')
        try:
            row['t0']=time.monotonic();time.sleep(delay);row['td']=time.monotonic()
            ack=self.patch(s['target_node'],s['target_replicas']);row['ta']=time.monotonic()
            row['generation']=ack['metadata']['generation']
            pods=self.ready(s['target_node'],s['target_replicas']);row['t_ready']=time.monotonic()
            new=[p for p in pods if p['metadata']['uid'] not in old]
            expected=1 if s['kind']=='migration' else s['target_replicas']-1
            if len(new)!=expected:raise RuntimeError('New replica count does not match fixed action')
            checks=[self.verify(p,s['fixture'],s['target_node']) for p in new]
            row.update(tb=max(p['t_end'] for p in checks),verified_replicas=checks,status='verified')
        except Exception as exc:row.update(status='verification_failed',terminal=time.monotonic(),error=repr(exc))
        row['D_s']=row['td']-row['t0'];row['Ta_s']=row['ta']-row['t0'] if 'ta' in row else None
        row['Tb_s']=row['tb']-row['t0'] if 'tb' in row else None
        with (self.out/'records.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
        print(json.dumps({k:row.get(k) for k in ['scenario','kind','repeat','injected_delay_s','status','D_s','Ta_s','Tb_s','error']}),flush=True)
        return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--scenarios',default='all');p.add_argument('--repeats',type=int,default=10)
    p.add_argument('--delays',default='0,0.1,0.5,2')
    args=p.parse_args();args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=False)
    data=BASE/'edge-scenarios.json';all_scenarios=json.loads(data.read_text())
    ids=set(args.scenarios.split(','));scenarios=all_scenarios if args.scenarios=='all' else [s for s in all_scenarios if s['id'] in ids]
    assert scenarios;delays=[float(x) for x in args.delays.split(',')]
    manifest=dict(seed=42,scenario_count=len(scenarios),repeats=args.repeats,delays_s=delays,
        scenarios_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        endpoint='all requested new pods Ready and each returns correct image through fixed API proxy',
        poll_s=.05,warm_module_and_image_caches=True,complete_baseline_pod_cleanup=True)
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.out/'measurement-code.py').write_bytes(Path(__file__).read_bytes())
    edge=Edge(args.out);rows=[];rng=random.Random(42)
    try:
        edge.start()
        for s in scenarios:
            edge.netem(s['link_delay_ms']);edge.warm(s['fixture'])
            for repeat in range(args.repeats):
                order=list(delays);rng.shuffle(order)
                for index,delay in enumerate(order):rows.append(edge.measure(s,delay,repeat,index))
    finally:
        if edge.proxy is not None:
            try:edge.patch('k3d-jev-e2-pilot-agent-0',1);edge.ready('k3d-jev-e2-pilot-agent-0',1,clear_old=True)
            finally:edge.stop()
    expected=len(scenarios)*args.repeats*len(delays)
    summary=dict(expected=expected,records=len(rows),verified=sum(r['status']=='verified' for r in rows),
        complete=len(rows)==expected,formal=len(scenarios)==30 and args.repeats==10 and set(delays)=={0.,.1,.5,2.})
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary,flush=True)


if __name__=='__main__':main()
