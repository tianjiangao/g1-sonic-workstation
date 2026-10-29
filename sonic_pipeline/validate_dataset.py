"""Full offline numeric/video checks plus the pinned Isaac-GR00T reader."""
import argparse,json,subprocess
from pathlib import Path
from fractions import Fraction
from sonic_pipeline.manifest import sha
import numpy as np
import pyarrow.parquet as pq
from sonic_pipeline.policy_guard import check_official_sources
SOURCE_VERSIONS=check_official_sources()
from sonic_pipeline.dex1_modality import CONFIG
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.data.stats import generate_stats,generate_rel_stats
from gr00t.data.dataset.lerobot_episode_loader import LeRobotEpisodeLoader
from gr00t.data.dataset.sharded_single_step_dataset import extract_step_data
from sonic_pipeline.settings import FPS,SCHEMA

def scan_parquet(file):
 table=pq.read_table(file);n=table.num_rows
 if n<41:raise ValueError('Episode too short for action horizon')
 ts=np.asarray(table['timestamp'].to_numpy(),dtype=float)
 if not np.isfinite(ts).all() or abs(ts[0])>1e-5 or not np.allclose(np.diff(ts),1/FPS,atol=1e-5,rtol=0):raise ValueError('Nonmonotonic or irregular dataset timestamps')
 for key,width in [('observation.body',29),('observation.dex1',2),('observation.projected_gravity',3),('action.motion_token',64),('action.dex1',2)]:
  a=np.asarray(table[key].to_pylist(),dtype=np.float32)
  if a.shape!=(n,width) or not np.isfinite(a).all():raise ValueError('Invalid full column '+key)
  if key=='action.dex1' and not np.all((a>=-.01)&(a<=5.41)):raise ValueError('Dex1 action range')
 tasks=np.asarray(table['task_index'].to_numpy())
 if len(tasks)!=n or np.any(tasks<0):raise ValueError('Invalid task indices')
 return n,set(int(x) for x in tasks)

def scan_video(file,n):
 result=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_frames','-show_entries','stream=nb_read_frames,width,height,avg_frame_rate:frame=best_effort_timestamp_time','-of','json',str(file)],capture_output=True,text=True,check=True,timeout=300)
 if result.stderr.strip():raise ValueError('Video decode errors: '+result.stderr[:200])
 decoded=json.loads(result.stdout);stream=decoded['streams'][0];times=np.asarray([float(f['best_effort_timestamp_time']) for f in decoded['frames']])
 if int(stream['nb_read_frames'])!=n or len(times)!=n or (stream['height'],stream['width'])!=(480,640) or Fraction(stream['avg_frame_rate'])!=FPS:raise ValueError('Video/table shape, fps or frame count mismatch')
 if not np.isfinite(times).all() or abs(times[0])>1e-5 or not np.allclose(np.diff(times),1/FPS,atol=1e-5,rtol=0):raise ValueError('Invalid video PTS')
 return {'frames':n,'fps':FPS,'width':640,'height':480}

def validate(path):
 path=Path(path)
 if (path/'dataset-acceptance.json').exists():
  from sonic_pipeline.acceptance import verify_acceptance
  receipt=json.loads((path/'dataset-acceptance.json').read_text());verify_acceptance(path,engineering=receipt.get('engineering_only',False))
  return json.loads((path/'reader-validation.json').read_text())
 from sonic_pipeline.acceptance import file_inventory
 file_inventory(path)  # reject links before reading or writing stats
 pro=json.loads((path/'pipeline-provenance.json').read_text())
 if pro.get('schema')!=SCHEMA:raise ValueError('Wrong dataset schema')
 generate_stats(path);generate_rel_stats(path,EmbodimentTag.NEW_EMBODIMENT)
 loader=LeRobotEpisodeLoader(path,CONFIG)
 if not len(loader):raise ValueError('Empty training dataset')
 info=json.loads((path/'meta/info.json').read_text());tasks={int(json.loads(x)['task_index']) for x in (path/'meta/tasks.jsonl').read_text().splitlines() if x.strip()}
 report=[]
 if len(loader)!=len(pro['episodes']):raise ValueError('Cleaning changed episode mapping; explicit provenance remapping required')
 for i in range(len(loader)):
  chunk=i//info.get('chunks_size',1000)
  n,used=scan_parquet(path/info['data_path'].format(episode_chunk=chunk,episode_index=i))
  if not used<=tasks:raise ValueError('Unknown task label')
  if n!=pro['episodes'][i]['frames']:raise ValueError('Cleaning changed frame mapping; explicit provenance remapping required')
  videos={}
  for key in ('ego_view','left_wrist','right_wrist'):
   rel=info['video_path'].format(episode_chunk=chunk,episode_index=i,video_key='observation.images.'+key)
   videos[key]=scan_video(path/rel,n)
  episode=loader[i]
  for at in sorted(set([0,max(0,len(episode)//2-20),len(episode)-40])):
   item=extract_step_data(episode,at,CONFIG,EmbodimentTag.NEW_EMBODIMENT)
   action=np.concatenate(list(item.actions.values()),axis=-1);state=np.concatenate(list(item.states.values()),axis=-1)
   if action.shape!=(40,66) or state.shape!=(1,34) or not np.isfinite(action).all() or not np.isfinite(state).all():raise ValueError('Wrong/nonfinite training contract')
   if set(item.images)!={'ego_view','left_wrist','right_wrist'}:raise ValueError('Missing training camera')
  report.append({'episode':i,'frames':n,'sample_action_shape':[40,66],'sample_state_shape':[1,34],'cameras':3,'videos':videos})
 artifacts={str(p.relative_to(path)):sha(p) for p in path.rglob('*') if p.is_file() and (str(p.relative_to(path)).startswith(('data/','meta/','videos/')) or p.name in ('pipeline-provenance.json','human-review.json'))}
 result={'artifact_sha256':artifacts,'official_source_versions':SOURCE_VERSIONS,'actual_gr00t_reader':'PASS','full_numeric_scan':True,'full_video_decode':True,'reader_windows_per_episode':3,'episodes':report,'embodiment':'NEW_EMBODIMENT','schema':SCHEMA,'task_success_verified':False}
 (path/'reader-validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);a=p.parse_args();validate(a.dataset)
