"""Thirty fixed migration/scale scenarios, with frozen image inputs and output oracle."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import numpy as np
from PIL import Image

BASE=Path(__file__).resolve().parent


def generate():
    folder=BASE/'image-inputs';folder.mkdir(exist_ok=True)
    fixtures=[];rng=np.random.default_rng(42)
    for i,side in enumerate([128,256,512,1024,1536],1):
        pixels=rng.integers(0,256,(side,side,3),dtype=np.uint8)
        image=Image.fromarray(pixels);buf=BytesIO();image.save(buf,format='PNG');raw=buf.getvalue()
        path=folder/f'frame-{side}.png';path.write_bytes(raw)
        # Freeze the service contract oracle once, before measuring execution.
        oracle=image.convert('L').resize((64,64)).tobytes()
        fixtures.append(dict(id=f'W{i}',image=str(path.relative_to(BASE)),width=side,height=side,bytes=len(raw),
          input_sha256=hashlib.sha256(raw).hexdigest(),expected_gray_pixels_sha256=hashlib.sha256(oracle).hexdigest(),
          origin='procedural RGB fixture, seed42; not natural-image accuracy evidence'))
    scenarios=[]
    for remote_ms in [10,25]:
        for fixture in fixtures:
            scenarios.append(dict(id=f'E{len(scenarios)+1:02d}',kind='migration',fixture=fixture,
                baseline_node='k3d-jev-e2-pilot-agent-1',baseline_replicas=1,
                target_node='k3d-jev-e2-pilot-agent-0',target_replicas=1,
                link_delay_ms={'k3d-jev-e2-pilot-agent-0':1,'k3d-jev-e2-pilot-agent-1':remote_ms},
                intent=f"Move image workload {fixture['id']} from remote site B to site A near the fixed control/probe client."))
    for node in ['k3d-jev-e2-pilot-agent-0','k3d-jev-e2-pilot-agent-1']:
        for replicas in [2,3]:
            for fixture in fixtures:
                scenarios.append(dict(id=f'E{len(scenarios)+1:02d}',kind='scale',fixture=fixture,
                    baseline_node=node,baseline_replicas=1,target_node=node,target_replicas=replicas,
                    link_delay_ms={'k3d-jev-e2-pilot-agent-0':1,'k3d-jev-e2-pilot-agent-1':25},
                    intent=f"Expand image workload {fixture['id']} on {node} from one to {replicas} replicas."))
    assert len(scenarios)==30
    (BASE/'edge-scenarios.json').write_text(json.dumps(scenarios,indent=2)+'\n')
    print('30 edge scenarios, five frozen image workloads',flush=True)


if __name__=='__main__':generate()
