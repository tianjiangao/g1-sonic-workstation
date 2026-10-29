"""G1+Dex1 capture contract. Receipt time is never called sensor time."""
import json
import math
import os
from pathlib import Path

REQUIRED = ('g1_debug','manager_state','robot_config','dex1_left_state','dex1_right_state',
            'dex1_left_cmd','dex1_right_cmd','camera_head','camera_left','camera_right')
CAMERAS={'camera_head':'ego_view','camera_left':'left_wrist','camera_right':'right_wrist'}

def vector(value,n):
    if len(value)!=n or not all(math.isfinite(float(x)) for x in value):
        raise ValueError('nonfinite or incorrect vector length')
    return [float(x) for x in value]

def make_frame(latest,now):
    for key in REQUIRED:
        if key not in latest: raise ValueError('missing '+key)
        limit=30 if key=='robot_config' else (.5 if key.startswith('camera_') else .25)
        age=(now-latest[key]['mono_ns'])/1e9
        if not 0<=age<=limit:raise ValueError('stale '+key)
    state=latest['g1_debug']['data']
    frame={'mono_ns':now,'observation.body':vector(state['body_q'],29),
           'action.body':vector(state['last_action'],29),
           'observation.dex1':vector([latest['dex1_'+s+'_state']['data']['q'] for s in ('left','right')],2),
           'action.dex1':vector([latest['dex1_'+s+'_cmd']['data']['q'] for s in ('left','right')],2),
           'source_receipts':{k:{'mono_ns':v['mono_ns'],'epoch_ns':v['epoch_ns']} for k,v in latest.items()},
           'images':{role:latest[k]['data']['path'] for k,role in CAMERAS.items()},
           'image_shapes':{role:latest[k]['data']['shape'] for k,role in CAMERAS.items()}}
    return frame

class Episode:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=False)
        (self.path/'images').mkdir()
        self.frames=(self.path/'frames.jsonl').open('x',buffering=1)
        self.events=(self.path/'events.jsonl').open('x',buffering=1)
        self.count=0;self.closed=False
        self._meta('recording',False)
    def _meta(self,reason,complete):
        p=self.path/'episode.json';tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps({'schema':'g1-29-dex1-v1','complete':complete,'reason':reason,
          'frames':self.count,'sensor_clock_synchronized':False,'timestamp_basis':'workstation receipt monotonic_ns',
          'training_ready':False},indent=2));tmp.replace(p)
    def append(self,frame):
        self.frames.write(json.dumps(frame,allow_nan=False)+'\n');self.count+=1
    def close(self,reason):
        if self.closed:return
        for f in (self.frames,self.events):f.flush();os.fsync(f.fileno());f.close()
        self._meta(reason,reason=='operator_stop' and self.count>0);self.closed=True

def schema():
    features={}
    for key,n,names in [('observation.body',29,[f'mujoco_body_{i}' for i in range(29)]),
                        ('action.body',29,[f'mujoco_body_{i}' for i in range(29)]),
                        ('observation.dex1',2,['physical_left_q_rad','physical_right_q_rad']),
                        ('action.dex1',2,['physical_left_command_q_rad','physical_right_command_q_rad'])]:
        features[key]={'dtype':'float32','shape':(n,),'names':names}
    for role,width in [('ego_view',1280),('left_wrist',640),('right_wrist',640)]:
        features['observation.images.'+role]={'dtype':'video','shape':(480,width,3),'names':['height','width','channel']}
    modality={'state':{},'action':{},'video':{},'annotation':{}}
    for key in ('state','action'):
        for name,n in [('body',29),('dex1',2)]:
            modality[key][name]={'start':0,'end':n,'original_key':('observation' if key=='state' else 'action')+'.'+name}
    modality['video']={r:{'original_key':'observation.images.'+r} for r in CAMERAS.values()}
    return features,modality
