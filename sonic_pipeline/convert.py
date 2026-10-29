"""Offline raw-event replay -> pinned NVIDIA Gr00tDataExporter.

Only measured source events at/before the sample time are used. Missing/stale
64D tokens or Dex1 feedback fail the conversion; no fabricated hand labels.
"""
import argparse,bisect,json,math,os
from collections import defaultdict
from pathlib import Path
import cv2,numpy as np
from sonic_pipeline.manifest import fingerprint,approved
from sonic_pipeline.settings import SCHEMA,FPS
NEEDED=('g1_debug','manager_state','robot_config','dex1_left_state','dex1_right_state','dex1_left_cmd','dex1_right_cmd','camera_head','camera_left','camera_right')
ROLES={'camera_head':'ego_view','camera_left':'left_wrist','camera_right':'right_wrist'}
def vector(v,n):
 a=np.asarray(v,dtype=np.float32)
 if a.shape!=(n,) or not np.isfinite(a).all():raise ValueError(f'Expected {n} finite values')
 return a
class Timeline:
 def __init__(self,episode):
  self.path=Path(episode);self.context=json.loads((self.path/'context.json').read_text());rows=[json.loads(x) for x in (self.path/'frames.jsonl').read_text().splitlines()]
  if not rows:raise ValueError('Empty episode')
  times=[x['mono_ns'] for x in rows]
  if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Nonmonotonic recorded grid')
  self.start=times[0];self.end=times[-1];self.events=defaultdict(list)
  for k,v in self.context['latest'].items():
   if k in NEEDED:self.events[k].append(v)
  with (self.path/'events.jsonl').open() as f:
   for line in f:
    v=json.loads(line);k=v['topic']
    if k in NEEDED:self.events[k].append({x:v[x] for x in ('data','mono_ns','epoch_ns')})
  self.times={}
  for k in NEEDED:
   self.events[k].sort(key=lambda x:x['mono_ns']);self.times[k]=[x['mono_ns'] for x in self.events[k]]
 def at(self,k,t):
  i=bisect.bisect_right(self.times[k],t)-1
  if i<0:raise ValueError('Missing source '+k)
  e=self.events[k][i];age=(t-e['mono_ns'])/1e9;limit=30 if k=='robot_config' else .5 if k.startswith('camera_') else .25
  if not 0<=age<=limit:raise ValueError(f'Stale {k}: {age:.3f}s')
  return e
 def grid(self,start_s=0.,end_s=None):
  duration=(self.end-self.start)/1e9
  if not math.isfinite(start_s) or start_s<0 or (end_s is not None and (not math.isfinite(end_s) or end_s>duration or end_s<=start_s)):raise ValueError('Invalid trim bounds')
  a=self.start+round(start_s*1e9);b=self.end if end_s is None else self.start+round(end_s*1e9)
  if a>b:raise ValueError('Empty trim interval')
  return range(a,b+1,1_000_000_000//FPS)
def schema():
 f={}
 for key,n in [('observation.body',29),('observation.dex1',2),('observation.projected_gravity',3),('action.motion_token',64),('action.dex1',2)]:f[key]={'dtype':'float32','shape':(n,),'names':[str(i) for i in range(n)]}
 for role in ROLES.values():f['observation.images.'+role]={'dtype':'video','shape':(480,640,3),'names':['height','width','channel']}
 def part(key,a,b):return {'start':a,'end':b,'original_key':key}
 m={'state':{'body':part('observation.body',0,29),'left_gripper':part('observation.dex1',0,1),'right_gripper':part('observation.dex1',1,2),'projected_gravity':part('observation.projected_gravity',0,3)},'action':{'motion_token':part('action.motion_token',0,64),'left_gripper':part('action.dex1',0,1),'right_gripper':part('action.dex1',1,2)},'video':{r:{'original_key':'observation.images.'+r} for r in ROLES.values()},'annotation':{'human.task_description':{'original_key':'task_index'}}}
 return f,m

def convert(entries,output,engineering_only=False,source_manifest=None):
 os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
 from sonic_pipeline.policy_guard import check_official_sources
 source_versions=check_official_sources()
 from gear_sonic.data.exporter import Gr00tDataExporter
 from gear_sonic.utils.data_collection.transforms import compute_projected_gravity
 out=Path(output)
 if out.exists():raise FileExistsError(out)
 if not entries:raise ValueError('No episodes selected')
 if not engineering_only:
  if not source_manifest:raise ValueError('Formal conversion requires explicit human review manifest')
  for e in entries:
   if e.get('decision')!='approved' or not e.get('reviewer') or not e.get('review_note'):raise ValueError('Human review required for formal conversion')
 prepared=[];canonical=None
 for entry in entries:
  ep=Path(entry['episode']);meta=json.loads((ep/'episode.json').read_text())
  if not meta['complete']:raise ValueError('Incomplete raw episode')
  if entry.get('fingerprints') and fingerprint(ep)!=entry['fingerprints']:raise ValueError('Source hash changed')
  timeline=Timeline(ep);grid=timeline.grid(entry.get('trim_start_s',0.),entry.get('trim_end_s'))
  if len(grid)<41:raise ValueError('Episode too short for 40-step action horizon')
  config=timeline.at('robot_config',grid[0])['data'];signature=json.dumps(config,sort_keys=True)
  if canonical is not None and canonical!=signature:raise ValueError('Controller config mismatch; do not merge distinct token controllers')
  canonical=signature
  # Validate every required stream/token before creating an output directory.
  for t in grid:
   for k in NEEDED:timeline.at(k,t)
   vector(timeline.at('g1_debug',t)['data']['token_state'],64)
  prepared.append((entry,timeline,grid))
 features,modalities=schema();exp=Gr00tDataExporter.create(save_root=out,fps=FPS,features=features,modality_config=modalities,task=entries[0]['task'],script_config={'schema':SCHEMA,'embodiment':'new_embodiment','action_dim':66,'state_dim':34,'fps':FPS,'action_horizon':40,'controller_config':json.loads(canonical),'token_alignment':'same-receipt-time WBC token_state, as-of50Hz; no interpolated labels','head_view':'left 640x480 lens from original1280x480 stereo','dex1_semantics':'physical left/right q radians, hardware routing retained','sensor_clocks_synchronized':False},robot_type='g1_sonic_dex1',overwrite_existing=False)
 provenance=[]
 try:
  for entry,timeline,grid in prepared:
   cache={};max_ages=defaultdict(float);tokens=[]
   for t in grid:
    e={k:timeline.at(k,t) for k in NEEDED};debug=e['g1_debug']['data'];q=vector(debug['base_quat'],4)
    if not .95<np.linalg.norm(q)<1.05:raise ValueError('Invalid base quaternion')
    frame={'observation.body':vector(debug['body_q'],29),'observation.dex1':vector([e['dex1_'+s+'_state']['data']['q'] for s in ('left','right')],2),'observation.projected_gravity':compute_projected_gravity(q).astype(np.float32),'action.motion_token':vector(debug['token_state'],64),'action.dex1':vector([e['dex1_'+s+'_cmd']['data']['q'] for s in ('left','right')],2),'task':entry['task']}
    if not np.all((frame['action.dex1']>=-.01)&(frame['action.dex1']<=5.41)):raise ValueError('Dex1 command outside calibrated range')
    for k,role in ROLES.items():
     path=(timeline.path/e[k]['data']['path']).resolve()
     if not path.is_relative_to(timeline.path.resolve()):raise ValueError('Image outside raw episode')
     if path not in cache:
      from sonic_pipeline.manifest import sha
      if sha(path)!=e[k]['data']['sha256']:raise ValueError('Image hash mismatch')
      im=cv2.imread(str(path))
      expected=(480,1280,3) if k=='camera_head' else (480,640,3)
      if im is None or im.shape!=expected:raise ValueError('Image shape mismatch')
      if k=='camera_head':im=im[:,:640]
      cache[path]=im[:,:,::-1].copy()
     frame['observation.images.'+role]=cache[path]
    for k,v in e.items():max_ages[k]=max(max_ages[k],(t-v['mono_ns'])/1e9)
    tokens.append(frame['action.motion_token']);exp.add_frame(frame)
   exp.save_episode()
   provenance.append({'source_episode':str(timeline.path),'source_session':timeline.path.parent.name,'take':entry.get('take'),'raw_sha256':fingerprint(timeline.path),'split':entry.get('split','engineering'),'review':{k:entry.get(k) for k in ['decision','reviewer','review_note']},'trim_start_s':entry.get('trim_start_s',0),'trim_end_s':entry.get('trim_end_s'),'frames':len(grid),'max_source_age_s':dict(max_ages),'token_nonzero':bool(np.any(np.asarray(tokens)!=0)),'token_range':float(np.ptp(np.asarray(tokens),axis=0).max())})
 finally:exp.stop_video_writers()
 import av,pyarrow.parquet as pq
 validation=[]
 for i,p in enumerate(provenance):
  n=pq.read_table(out/exp.meta.get_data_file_path(i)).num_rows;videos={}
  for key in exp.meta.video_keys:
   with av.open(str(out/exp.meta.get_video_file_path(i,key))) as c:
    rate=float(c.streams.video[0].average_rate);count=sum(1 for _ in c.decode(video=0))
   if count!=n or rate!=FPS:raise ValueError('Exported video/table count or rate mismatch')
   videos[key]={'frames':count,'fps':rate}
  if n!=p['frames']:raise ValueError('Frame count changed')
  validation.append({'frames':n,'videos':videos})
 report={'schema':SCHEMA,'official_source_versions':source_versions,'format_validation':'PASS','engineering_only':engineering_only,'human_approved':not engineering_only,'source_manifest':source_manifest,'task_success_verified':False,'training_ready':False,'reason':'Requires explicit human success review, independent validation set, and model/adapter acceptance','episodes':provenance,'validation':validation}
 if source_manifest:
  review_doc=json.loads(Path(source_manifest).read_text());selected={e['episode'] for e in entries};review_doc['episodes']=[e for e in review_doc['episodes'] if e['episode'] in selected]
  (out/'human-review.json').write_text(json.dumps(review_doc,ensure_ascii=False,indent=2))
 (out/'pipeline-provenance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'output':str(out),'episodes':len(provenance),'frames':sum(x['frames'] for x in provenance),'engineering_only':engineering_only},ensure_ascii=False),flush=True);return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--manifest');p.add_argument('--split',choices=['train','validation','test'],default='train');p.add_argument('--engineering-episode');a=p.parse_args()
 if bool(a.manifest)==bool(a.engineering_episode):raise ValueError('Choose reviewed manifest OR explicitly engineering-only raw episode')
 entries=approved(a.manifest,a.split) if a.manifest else [{'episode':a.engineering_episode,'task':'ENGINEERING_ONLY: recorded task without success approval','decision':'engineering_only','take':json.loads((Path(a.engineering_episode)/'episode.json').read_text()).get('take_number')}]
 convert(entries,a.output,bool(a.engineering_episode),a.manifest)
if __name__=='__main__':main()
