"""Physical OSPF/BGP path intervention, with source reset and live packet probes."""
from pathlib import Path
import argparse
import hashlib
import json
import random
import re
import subprocess
import threading
import time

BASE=Path(__file__).resolve().parent


class Lab:
    def __init__(self,out):self.out=out

    def command(self,node,args,timeout=10,check=True):
        cmd=['docker','exec',f'clab-jev-e2-ring-r{node}']+args
        start=time.monotonic();r=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        end=time.monotonic()
        with (self.out/'commands.jsonl').open('a') as f:
            f.write(json.dumps(dict(t_start=start,t_end=end,command=cmd,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))+'\n')
        if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
        return r.stdout

    def vty(self,node,commands):
        args=['vtysh']
        for text in commands:args+=['-c',text]
        out=self.command(node,args)
        if '% Unknown command' in out or '% Configuration failed' in out:raise RuntimeError(out)
        return out

    def costs(self,node,clockwise,counterclockwise):
        return self.vty(node,['configure terminal','interface eth1',f'ip ospf cost {clockwise}',
                              'interface eth2',f'ip ospf cost {counterclockwise}','end'])

    def wait_route(self,s,interface,deadline=40):
        until=time.monotonic()+deadline;consecutive=0;route=None
        while time.monotonic()<until:
            route=self.command(s['source'],['ip','route','get',s['destination_ip']],check=False)
            if 'dev '+interface in route:
                consecutive+=1
                if consecutive==3:return route,time.monotonic()
            else:consecutive=0
            time.sleep(.05)
        raise RuntimeError('FIB did not settle on '+interface+': '+str(route))

    def ping(self,s):
        raw=self.command(s['source'],['ping','-c','3','-i','0.05','-W','2',
                          '-I',f"10.255.0.{s['source']}",s['destination_ip']],timeout=10)
        values=[float(x) for x in re.findall(r'time=([\d.]+) ms',raw)]
        if len(values)!=3 or '0% packet loss' not in raw:raise RuntimeError('Packet verification failed: '+raw)
        return raw,values

    def plane(self):
        data={}
        for node in range(1,9):
            bgp=json.loads(self.vty(node,['show bgp ipv4 unicast summary json']))
            ospf=json.loads(self.vty(node,['show ip ospf neighbor json']))
            assert len(bgp['peers'])==7 and all(p['state']=='Established' and p['pfxRcd']==1 for p in bgp['peers'].values())
            neighbors=[p for group in ospf['neighbors'].values() for p in group]
            assert len(neighbors)==2 and all(p['converged']=='Full' for p in neighbors)
            data[str(node)]=dict(bgp=bgp,ospf=ospf)
        return data

    def netem(self):
        for node in range(1,9):
            for iface,ms in [('eth1',5),('eth2',1)]:
                self.command(node,['tc','qdisc','replace','dev',iface,'root','netem','delay',str(ms)+'ms'])

    def baseline_barrier(self,s,timeout=60):
        start=time.monotonic();until=start+timeout
        expected={f"10.23.{s['source']}.1":10,
                  f"10.23.{(s['source']-2)%8+1}.2":100}
        def snapshot():
            states=[]
            for node in range(1,9):
                db=json.loads(self.vty(node,[f"show ip ospf database router 10.255.0.{s['source']} json"]))
                lsa=db['routerLinkStates']['areas']['0.0.0.0'][0]
                metrics={v['routerInterfaceAddress']:v['tos0Metric'] for v in lsa['routerLinks'].values()
                         if v['linkType']=='another Router (point-to-point)'}
                timer=self.vty(node,['show ip ospf'])
                states.append(dict(node=node,metrics=metrics,sequence=lsa['lsaSeqNumber'],
                                   checksum=lsa['checksum'],spf_inactive='SPF timer is inactive' in timer))
            good=all(x['metrics']==expected and x['spf_inactive'] for x in states)
            good=good and len({(x['sequence'],x['checksum']) for x in states})==1
            return good,states
        while time.monotonic()<until:
            good,states=snapshot()
            if good:
                quiet_start=time.monotonic();time.sleep(6)
                after,latest=snapshot()
                if after and [(x['sequence'],x['checksum']) for x in latest]==[(x['sequence'],x['checksum']) for x in states]:
                    return dict(start=start,end=time.monotonic(),quiet_start=quiet_start,quiet_s=6,states=latest)
            time.sleep(.1)
        raise RuntimeError('All-router baseline LSDB/SPF quiet barrier not reached')

    def continuous(self,s,path):
        node=f"clab-jev-e2-ring-r{s['source']}"
        script=f"echo $$ >/tmp/jev-e2-probe.pid; exec ping -i 0.1 -w 40 -I 10.255.0.{s['source']} {s['destination_ip']}"
        process=subprocess.Popen(['docker','exec',node,'sh','-c',script],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        def read():
            with path.open('w') as f:
                for line in process.stdout:
                    f.write(json.dumps(dict(observed_at=time.monotonic(),line=line.rstrip()))+'\n');f.flush()
        thread=threading.Thread(target=read);thread.start()
        return process,thread

    def end_continuous(self,node,process,thread):
        self.command(node,['sh','-c','if [ -f /tmp/jev-e2-probe.pid ]; then kill -TERM "$(cat /tmp/jev-e2-probe.pid)" 2>/dev/null || true; fi'],check=False)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
        thread.join(timeout=5)


def measure(lab,s,delay,repeat,index):
    source=s['source'];process=thread=None
    lab.costs(source,s['baseline']['eth1_cost'],s['baseline']['eth2_cost'])
    barrier=lab.baseline_barrier(s)
    baseline_route,_=lab.wait_route(s,'eth1');baseline_ping,baseline_rtt=lab.ping(s)
    row=dict(domain='transport',scenario=s['id'],source=source,destination=s['destination'],
             repeat=repeat,order=index,injected_delay_s=delay,baseline_route=baseline_route,baseline_rtt_ms=baseline_rtt,
             status='pending',rtt_verification_bound_ms=s['rtt_verification_bound_ms'])
    row['baseline_barrier']=barrier
    try:
        log=lab.out/f"ping-{s['id']}-r{repeat}-d{delay}.jsonl";process,thread=lab.continuous(s,log)
        row['continuous_ping_log']=str(log.relative_to(BASE))
        row['t0']=time.monotonic();time.sleep(delay);row['td']=time.monotonic()
        row['configuration_ack']=lab.costs(source,s['action']['eth1_cost'],s['action']['eth2_cost'])
        row['ta']=time.monotonic();route,fib=lab.wait_route(s,'eth2');row['t_fib']=fib;row['route']=route
        if 'via '+s['required_next_hop'] not in route:raise RuntimeError('Wrong next hop: '+route)
        trace=lab.command(source,['traceroute','-n','-q','1','-w','1','-m','12','-s',f'10.255.0.{source}',s['destination_ip']],timeout=15)
        row['traceroute']=trace
        hops=[line for line in trace.splitlines() if re.match(r'\s*\d+\s+',line)]
        if not hops or s['required_next_hop'] not in hops[0] or s['destination_ip'] not in hops[-1]:
            raise RuntimeError('Actual path not verified: '+trace)
        ping,rtt=lab.ping(s);row.update(ping=ping,rtt_ms=rtt)
        if max(rtt)>s['rtt_verification_bound_ms']:raise RuntimeError('RTT did not meet declared path bound')
        row.update(tb=time.monotonic(),status='verified')
    except Exception as exc:
        row.update(status='verification_failed',error=repr(exc),terminal=time.monotonic())
    finally:
        if process is not None:lab.end_continuous(source,process,thread)
    if 't0' in row:
        row['D_s']=row['td']-row['t0'];row['Ta_s']=row['ta']-row['t0'] if 'ta' in row else None
        row['Tb_s']=row['tb']-row['t0'] if 'tb' in row else None
    with (lab.out/'records.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:row.get(k) for k in ['scenario','repeat','injected_delay_s','status','D_s','Ta_s','Tb_s','rtt_ms','error']}),flush=True)
    return row


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--scenario-count',type=int,default=30);p.add_argument('--repeats',type=int,default=10)
    p.add_argument('--scenarios',default='all')
    args=p.parse_args();args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'measurement-code.py').write_bytes(Path(__file__).read_bytes())
    data_path=BASE/'transport-scenarios.json';scenarios=json.loads(data_path.read_text())[:args.scenario_count]
    if args.scenarios!='all':
        ids=set(args.scenarios.split(','));scenarios=[s for s in scenarios if s['id'] in ids]
        assert {s['id'] for s in scenarios}==ids
    manifest=dict(seed=42,scenario_count=len(scenarios),repeats=args.repeats,delays_s=[0.,.1,.5,2.],
                  scenarios_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  baseline_quiet_s=6,baseline_requires_all_router_lsdb_agreement=True,
                  protocol_timers='native: LSA minimum 5000ms, arrival 1000ms, SPF hold maximum 5000ms',
                  scope='physical sparse intervention; calibration if fewer than 30 scenes or 10 repeats')
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    lab=Lab(args.out);(args.out/'planes.json').write_text(json.dumps(lab.plane(),indent=2)+'\n');lab.netem()
    rng=random.Random(42);rows=[]
    for scenario in scenarios:
        try:
            for repeat in range(args.repeats):
                delays=[0.,.1,.5,2.];rng.shuffle(delays)
                for index,delay in enumerate(delays):rows.append(measure(lab,scenario,delay,repeat,index))
        finally:lab.costs(scenario['source'],10,10)
    expected=len(scenarios)*args.repeats*4
    summary=dict(expected=expected,records=len(rows),verified=sum(r['status']=='verified' for r in rows),
                 complete=len(rows)==expected,formal=len(scenarios)==30 and args.repeats==10)
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary,flush=True)


if __name__=='__main__':main()
