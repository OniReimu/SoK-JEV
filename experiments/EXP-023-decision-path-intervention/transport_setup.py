"""Eight-router OSPF+iBGP ring; immutable source config, no model calls."""
from pathlib import Path
import argparse
import json
import os
import subprocess

BASE=Path(__file__).resolve().parent
LAB=BASE/'transport-ring'
IMAGE=os.environ.get('JEV_E2_FRR_IMAGE','quay.io/frrouting/frr@sha256:54aca1fe272e8ab298aba491211d4b4a303ff95aa42cf7ff6487b14dc7b4e513')


def generate():
    LAB.mkdir(exist_ok=True)
    for i in range(1,9):
        prev=8 if i==1 else i-1
        text=f'''frr defaults traditional
hostname r{i}
service integrated-vtysh-config
ip forwarding
interface eth1
 ip address 10.23.{i}.1/30
 ip ospf network point-to-point
 ip ospf cost 10
interface eth2
 ip address 10.23.{prev}.2/30
 ip ospf network point-to-point
 ip ospf cost 10
interface lo
 ip address 10.255.0.{i}/32
 ip address 198.18.{i}.1/32
router ospf
 ospf router-id 10.255.0.{i}
 network 10.23.0.0/16 area 0
 network 10.255.0.{i}/32 area 0
router bgp 65023
 bgp router-id 10.255.0.{i}
'''
        for j in range(1,9):
            if j!=i:text+=f' neighbor 10.255.0.{j} remote-as 65023\n neighbor 10.255.0.{j} update-source lo\n'
        text+=' address-family ipv4 unicast\n'+f'  network 198.18.{i}.1/32\n'
        for j in range(1,9):
            if j!=i:text+=f'  neighbor 10.255.0.{j} activate\n'
        text+=' exit-address-family\n'
        (LAB/f'r{i}.conf').write_text(text)
    (LAB/'daemons').write_text('zebra=yes\nospfd=yes\nbgpd=yes\nvtysh_enable=yes\nzebra_options=" -A 127.0.0.1 -s 90000000"\nospfd_options=" -A 127.0.0.1"\nbgpd_options=" -A 127.0.0.1"\n')
    (LAB/'vtysh.conf').write_text('service integrated-vtysh-config\n')
    text='name: jev-e2-ring\nmgmt:\n  network: jev-e2-ring-mgmt\n  ipv4-subnet: 192.168.252.0/24\ntopology:\n  defaults:\n    kind: linux\n    image: '+IMAGE+'\n    sysctls:\n      net.ipv4.ip_forward: "1"\n      net.ipv4.conf.all.rp_filter: "0"\n  nodes:\n'
    for i in range(1,9):text+=f'    r{i}:\n      binds:\n        - r{i}.conf:/etc/frr/frr.conf\n        - daemons:/etc/frr/daemons\n        - vtysh.conf:/etc/frr/vtysh.conf\n'
    text+='  links:\n'
    for i in range(1,9):text+=f'    - endpoints: [r{i}:eth1, r{(i%8)+1}:eth2]\n'
    (LAB/'ring.clab.yml').write_text(text)
    scenarios=[]
    for i in range(1,9):
        for offset in [2,3,4,5]:
            dest=(i-1+offset)%8+1;prev=8 if i==1 else i-1
            scenarios.append(dict(id=f'T{len(scenarios)+1:02d}',source=i,destination=dest,offset=offset,
              prefix=f'198.18.{dest}.1/32',destination_ip=f'198.18.{dest}.1',
              baseline=dict(eth1_cost=10,eth2_cost=100),action=dict(eth1_cost=200,eth2_cost=100),
              baseline_interface='eth1',required_interface='eth2',required_next_hop=f'10.23.{prev}.1',
              intent=f'Route service prefix 198.18.{dest}.1/32 from r{i} without its clockwise link.',
              latency_profile=dict(clockwise_ms=5,counterclockwise_ms=1),
              # Verification bound derives from configured hops, with a declared 10ms scheduling margin.
              rtt_verification_bound_ms=(8-offset)*1+min(offset,8-offset)*5+10))
    (BASE/'transport-scenarios.json').write_text(json.dumps(scenarios[:30],indent=2)+'\n')


def deploy(run):
    root=BASE.parents[1]
    cmd=['docker','run','--rm','--privileged','--network','host','--pid','host',
         '-v','/var/run/docker.sock:/var/run/docker.sock','-v','/var/run/netns:/var/run/netns',
         '-v',f'{root}:{root}','-w',str(LAB),'ghcr.io/srl-labs/clab:0.79.0',
         'containerlab','deploy','-t','ring.clab.yml']
    (run/'transport-deploy-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    with (run/'transport-deploy.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=100)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False);generate();deploy(args.out)
    print('Eight-router ring deployed',flush=True)
