"""Content-bound local acceptance, shared by SSH handoff and formal training."""
import hashlib,json
from pathlib import Path
from sonic_pipeline.manifest import sha
from sonic_pipeline.settings import SCHEMA
RECEIPT='dataset-acceptance.json'

def file_inventory(path):
 root=Path(path).resolve();files={}
 if not root.is_dir():raise ValueError('Dataset directory missing')
 for p in sorted(root.rglob('*')):
  if p.is_symlink():raise ValueError('Dataset symlink is forbidden: '+str(p))
  if p.is_file() and p.relative_to(root).as_posix()!=RECEIPT:files[p.relative_to(root).as_posix()]=sha(p)
 return files

def inventory_id(files):
 return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check_review(pro,path):
 if pro.get('engineering_only') or not pro.get('human_approved'):raise ValueError('Engineering/unreviewed data cannot authorize formal training')
 snapshot=Path(path)/'human-review.json'
 if not snapshot.is_file():raise ValueError('Missing bound human review snapshot')
 reviews=json.loads(snapshot.read_text())['episodes']
 if not pro.get('episodes'):raise ValueError('Empty reviewed dataset')
 for e in pro['episodes']:
  decision=e.get('review',{})
  if decision.get('decision')!='approved' or not decision.get('reviewer') or not decision.get('review_note'):raise ValueError('Missing per-episode human review')
  if e.get('split') not in ('train','validation','test'):raise ValueError('Missing reviewed split')
  raw=e.get('raw_sha256',{})
  from sonic_pipeline.manifest import FILES
  if set(raw)!=set(FILES) or any(not isinstance(h,str) or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in raw.values()):raise ValueError('Human review lacks complete raw source fingerprints')
  matches=[x for x in reviews if x['episode']==e['source_episode'] and x.get('fingerprints')==e.get('raw_sha256')]
  if len(matches)!=1:raise ValueError('Human review/source hash mismatch')
  r=matches[0]
  if r.get('decision')!='approved' or r.get('split')!=e['split'] or any(r.get(k)!=decision.get(k) for k in ('reviewer','review_note')):raise ValueError('Human review decision mismatch')
  if any(r.get(k)!=e.get(k) for k in ('trim_start_s','trim_end_s')):raise ValueError('Human review trim mismatch')

def verify_reader(path):
 p=Path(path);pro=json.loads((p/'pipeline-provenance.json').read_text())
 if pro.get('schema')!=SCHEMA:raise ValueError('Wrong dataset schema')
 clean=pro.get('official_cleaning',{})
 if not clean.get('processor_sha256') or clean.get('smpl_cleaning_disabled') is not True:raise ValueError('Missing official cleaning receipt')
 reader=json.loads((p/'reader-validation.json').read_text())
 if reader.get('actual_gr00t_reader')!='PASS' or reader.get('full_numeric_scan') is not True or reader.get('full_video_decode') is not True:raise ValueError('Full dataset/real reader validation required')
 from sonic_pipeline.policy_guard import check_policy
 contract=check_policy();versions=pro.get('official_source_versions',{})
 if any(versions.get(k)!=contract[k] for k in ('wbc_commit','groot_commit')):raise ValueError('Official source version does not match fixed policy')
 if versions!=clean.get('official_source_versions') or versions!=reader.get('official_source_versions'):raise ValueError('Conversion/cleaning/reader official source versions differ')
 expected_processor=versions.get('wbc_files_sha256',{}).get('gear_sonic/scripts/process_dataset.py')
 if not expected_processor or clean['processor_sha256']!=expected_processor:raise ValueError('Official processor source hash mismatch')
 files=file_inventory(p);hashes=reader.get('artifact_sha256',{})
 required={n for n in files if n.startswith(('data/','meta/','videos/')) or n in ('pipeline-provenance.json','human-review.json')}
 if not required or set(hashes)!=required:raise ValueError('Reader hash inventory incomplete')
 for name,digest in hashes.items():
  if files.get(name)!=digest:raise ValueError('Reader validated artifact hash changed: '+name)
 return pro,files

def accept_dataset(path,engineering=False):
 p=Path(path);target=p/RECEIPT
 if target.exists():raise FileExistsError('Acceptance exists; verify it, never overwrite: '+str(target))
 # Check review before trusting any acceptance flags or regenerating hashes.
 pro=json.loads((p/'pipeline-provenance.json').read_text())
 if not engineering:check_review(pro,p)
 elif pro.get('engineering_only') is not True or pro.get('human_approved') is not False:raise ValueError('Engineering mode requires explicitly engineering-only, unapproved data')
 pro,files=verify_reader(p)
 result={'schema':'sonic-local-acceptance-v1','dataset_id':inventory_id(files),'file_sha256':files,'engineering_only':engineering,'formal_training_eligible':not engineering,'task_success_verified':False,'robot_control_started':False}
 with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
 return result

def verify_acceptance(path,engineering=False):
 p=Path(path)
 if not (p/RECEIPT).is_file():raise ValueError('Missing local dataset acceptance receipt')
 receipt=json.loads((p/RECEIPT).read_text());files=file_inventory(p)
 if receipt.get('schema')!='sonic-local-acceptance-v1' or receipt.get('file_sha256')!=files or receipt.get('dataset_id')!=inventory_id(files):raise ValueError('Accepted dataset inventory or hash changed')
 if engineering:
  if receipt.get('engineering_only') is not True or receipt.get('formal_training_eligible') is not False:raise ValueError('Engineering handoff requires engineering-only receipt')
 elif receipt.get('engineering_only') or not receipt.get('formal_training_eligible'):raise ValueError('Engineering data cannot authorize formal handoff/training')
 pro,_=verify_reader(p)
 if not engineering:check_review(pro,p)
 elif not pro.get('engineering_only') or pro.get('human_approved'):raise ValueError('Engineering provenance changed')
 return receipt
