"""File-only G1 replay. Observations are radians in serialized MuJoCo order.
No DDS, ZMQ, inference, physics stepping, or control client imports.
"""
from bisect import bisect_right
import hashlib,json,math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
ROOT=Path(__file__).resolve().parents[1]
NAMES=tuple(f'{side}_{name}_joint' for side in ('left','right') for name in ('hip_pitch','hip_roll','hip_yaw','knee','ankle_pitch','ankle_roll'))+('waist_yaw_joint','waist_roll_joint','waist_pitch_joint')+tuple(f'{side}_{name}_joint' for side in ('left','right') for name in ('shoulder_pitch','shoulder_roll','shoulder_yaw','elbow','wrist_roll','wrist_pitch','wrist_yaw'))
MODEL_DIR=Path(__file__).parent/json.loads((Path(__file__).parent/'model_config.json').read_text())['asset_directory']
ROLES=('ego_view','left_wrist','right_wrist')
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def fingerprints(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def vector(value,n=29):
    if not isinstance(value,list) or len(value)!=n or not all(type(x) in (int,float) and math.isfinite(x) for x in value):raise ValueError(f'Expected finite measured {n}D vector; no target/token substitution')
    return value

def _lines(path):
    with path.open() as f:
        for line in f:
            if line.strip():yield json.loads(line)

def verify_sources():
    contract=json.loads((Path(__file__).parent/'source-contract.json').read_text())
    for name,digest in contract.items():
        if sha(ROOT/name)!=digest:raise ValueError('Mapping source changed; audit required: '+name)
    return contract

class Episode:
    def __init__(self,path):
        verify_sources();self.path=Path(path).resolve()
        self.meta=json.loads((self.path/'episode.json').read_text());ctx=json.loads((self.path/'context.json').read_text())
        if not self.meta.get('complete'):raise ValueError('Episode not complete; refusing replay as a valid capture')
        self.kind='SYNTHETIC_ONLY' if ctx.get('session',{}).get('synthetic') else 'REAL_CAPTURE'
        self.task=ctx.get('session',{}).get('task','');self.frames=[];self.provenance_matches=0
        for f in _lines(self.path/'frames.jsonl'):
            q=vector(f.get('observation.body'));target=vector(f['action.body']) if 'action.body' in f else None
            if type(f.get('mono_ns')) is not int:raise ValueError('Missing recorded monotonic timestamp')
            images=f.get('images',{})
            if not set(ROLES).issubset(images):raise ValueError('Missing recorded camera view')
            for role,relative in images.items():
                image=(self.path/relative).resolve()
                if not image.is_relative_to(self.path) or not image.is_file():raise ValueError('Missing or unsafe recorded image')
            self.frames.append({'mono_ns':f['mono_ns'],'q':q,'target':target,'images':images,
                'dex1_state':vector(f['observation.dex1'],2) if 'observation.dex1' in f else None,
                'dex1_command':vector(f['action.dex1'],2) if 'action.dex1' in f else None,
                'receipt':f.get('source_receipts',{}).get('g1_debug',{}).get('mono_ns'),
                'source_receipts':f.get('source_receipts',{})})
        if not self.frames or len(self.frames)!=self.meta.get('frames'):raise ValueError('Recorded frame count mismatch')
        self.times=[(f['mono_ns']-self.frames[0]['mono_ns'])/1e9 for f in self.frames]
        if any(b<=a for a,b in zip(self.times,self.times[1:])):raise ValueError('Nonmonotonic replay timestamps')
        # Verify serialized observations against exact original g1_debug receipts,
        # not against human poses, latent tokens, or generated simulator states.
        wanted={f['receipt'] for f in self.frames};raw={}
        initial=ctx.get('latest',{}).get('g1_debug')
        if initial and initial.get('mono_ns') in wanted:raw[initial['mono_ns']]=initial['data']
        for e in _lines(self.path/'events.jsonl'):
            if e.get('topic')=='g1_debug' and e.get('mono_ns') in wanted:raw[e['mono_ns']]=e['data']
        for f in self.frames:
            original=raw.get(f['receipt'])
            if original is None:raise ValueError('Missing original g1_debug receipt for measured pose')
            measured=vector(original.get('body_q'))
            if not np.allclose(f['q'],measured,atol=1e-9,rtol=0):raise ValueError('Observation differs from original robot feedback')
            if 'body_q_measured' in original and not np.allclose(measured,vector(original['body_q_measured']),atol=1e-9,rtol=0):raise ValueError('Ambiguous body_q measurement semantics')
            if f['target'] is not None and not np.allclose(f['target'],vector(original.get('last_action')),atol=1e-9,rtol=0):raise ValueError('Target angle source differs from last_action')
            self.provenance_matches+=1
        self.raw_first_observation=raw[self.frames[0]['receipt']]['body_q']
        self.duration=self.times[-1]
    def seek(self,seconds):return max(0,min(len(self.frames)-1,bisect_right(self.times,seconds)-1))
    def image(self,index,role):
        if role not in ROLES:raise ValueError('Unknown recorded image role')
        return (self.path/self.frames[index]['images'][role]).read_bytes()

class BodyModel:
    def __init__(self):
        verify_sources()
        from offline_replay.gripper import GripperStateAdapter
        asset=MODEL_DIR/'g1_sonic_dex1_passive.xml'
        build=json.loads((asset.parent/'build-report.json').read_text())
        if sha(asset)!=build['hashes'][asset.name]:raise ValueError('Passive model changed; audit required')
        for name,digest in build['mesh_sha256'].items():
            if sha(name)!=digest:raise ValueError('Mesh asset changed: '+name)
        self.model=mujoco.MjModel.from_xml_path(str(asset));self.data=mujoco.MjData(self.model)
        self.gripper=GripperStateAdapter();self.finger_addresses={};self.last_gripper=None
        for side in ('left','right'):
            for finger in (1,2):
                name=f'{side}_dex1_finger_joint_{finger}';j=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
                if j<0 or self.model.jnt_type[j]!=mujoco.mjtJoint.mjJNT_SLIDE:raise ValueError('Missing visual finger slide')
                self.finger_addresses[name]=int(self.model.jnt_qposadr[j])
        self.names=NAMES;self.addresses=[];self.axes=[];self.joint_ids=[]
        for name in NAMES:
            j=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_JOINT,name)
            if j<0 or self.model.jnt_type[j]!=mujoco.mjtJoint.mjJNT_HINGE:raise ValueError('Missing/invalid body hinge: '+name)
            self.joint_ids.append(j);self.addresses.append(int(self.model.jnt_qposadr[j]));self.axes.append(self.model.jnt_axis[j].copy())
        if len(set(self.addresses))!=29 or self.model.nq!=40 or self.model.nv!=39 or self.model.nu!=0:raise ValueError('Unexpected body model DOF/actuator contract')
        self.renderer=None;self.gl_renderer=None
    def apply(self,q,dex1=None,gripper_source="feedback"):
        q=np.asarray(q,dtype=float)
        if q.shape!=(29,) or not np.isfinite(q).all():raise ValueError('Expected finite 29D measured joints')
        self.data.qpos[:]=self.model.qpos0;self.data.qpos[self.addresses]=q
        if dex1 is not None:
            vector(dex1,2)
            self.last_gripper=self.gripper.map(dict(zip(('left','right'),dex1)),source=gripper_source)
            for name,value in self.last_gripper['joints'].items():self.data.qpos[self.finger_addresses[name]]=value
        self.data.qvel[:]=0
        mujoco.mj_forward(self.model,self.data)  # No integration or policy step.
    def render(self,q,azimuth=135,elevation=-15,distance=2.5,dex1=None,gripper_source="feedback",view="body"):
        self.apply(q,dex1,gripper_source)
        if self.renderer is None:
            self.renderer=mujoco.Renderer(self.model,height=480,width=640)
            from OpenGL.GL import glGetString,GL_RENDERER
            self.gl_renderer=glGetString(GL_RENDERER).decode()
        camera=mujoco.MjvCamera();camera.lookat[:]=[0,0,.78]
        if view in ('left','right'):
            body=mujoco.mj_name2id(self.model,mujoco.mjtObj.mjOBJ_BODY,view+'_dex1_base_link')
            camera.lookat[:]=self.data.xpos[body]+self.data.xmat[body].reshape(3,3).dot([.07,0,0])
            distance*=.14
        elif view!='body':raise ValueError('Unknown passive view')
        camera.distance=distance;camera.azimuth=azimuth;camera.elevation=elevation
        self.renderer.update_scene(self.data,camera=camera);return self.renderer.render()
    def close(self):
        if self.renderer:self.renderer.close()
