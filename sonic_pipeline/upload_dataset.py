"""Accepted-only nested SSH handoff. No training/control startup or raw deletion."""
import json,os,tarfile,tempfile,uuid,inspect
from pathlib import Path
from sonic_pipeline.acceptance import verify_acceptance
from sonic_pipeline.manifest import sha
from sonic_pipeline.remote import run,REMOTE_ROOT
from sonic_pipeline.policy_guard import check_policy

def receive_archive(stream,destination,expected,reusable=None):
 # Self-contained: same receiver is exercised locally in tests and over SSH.
 import hashlib,json,os,tarfile,uuid,shutil
 from pathlib import Path
 dest=Path(destination)
 def digest(p):
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  return h.hexdigest()
 def inventory(root):
  files={}
  for p in root.rglob('*'):
   if p.is_symlink():raise ValueError('Remote dataset symlink')
   if p.is_file():files[p.relative_to(root).as_posix()]=digest(p)
  return files
 if dest.is_symlink():raise ValueError('Destination symlink')
 if dest.exists():
  if inventory(dest)!=expected:raise ValueError('Existing destination differs; refusing overwrite')
  return {'remote_hash_verification':'PASS','remote_path':str(dest),'files':len(expected),'already_present':True}
 dest.parent.mkdir(parents=True,exist_ok=True)
 stage=dest.parent/('.'+dest.name+'.partial-'+uuid.uuid4().hex);stage.mkdir()
 # Reuse only verified bytes inside the same approved namespace; never hard-link.
 seen=set()
 for name,source_name in (reusable or {}).items():
  source=Path(source_name);relative=Path(name)
  if name not in expected or relative.is_absolute() or '..' in relative.parts or source.is_symlink() or not source.resolve().is_relative_to(dest.parent.resolve()) or digest(source)!=expected[name]:raise ValueError('Unsafe/corrupt remote reuse')
  target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
  if digest(target)!=expected[name]:raise ValueError('Remote reuse changed during copy')
  seen.add(name)
 # Partial files intentionally remain after a failure; never publish them as accepted.
 with tarfile.open(fileobj=stream,mode='r|') as archive:
  for item in archive:
   relative=Path(item.name)
   if relative.is_absolute() or '..' in relative.parts or not item.isfile() or item.name not in expected or item.name in seen:raise ValueError('Unsafe/unexpected archive member')
   seen.add(item.name);p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True)
   source=archive.extractfile(item)
   with p.open('xb') as out:
    for b in iter(lambda:source.read(1024*1024),b''):out.write(b)
 if inventory(stage)!=expected:raise ValueError('Remote dataset hash mismatch')
 # Refuse a concurrently-created destination as well; never merge into it.
 if dest.exists():raise FileExistsError('Concurrent destination exists')
 os.rename(stage,dest)
 return {'remote_hash_verification':'PASS','remote_path':str(dest),'files':len(expected),'already_present':False}

def reusable_files(destination,expected,approved_root):
 import hashlib
 from pathlib import Path
 dest=Path(destination);found={}
 if not dest.resolve().is_relative_to(Path(approved_root).resolve()):raise ValueError('Remote reuse path escapes approved root')
 if not dest.parent.exists():return found
 for package in dest.parent.iterdir():
  if not package.is_dir() or package.is_symlink():continue
  for name,digest in expected.items():
   if name in found:continue
   p=package/name
   if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to(dest.parent.resolve()):continue
   h=hashlib.sha256()
   with p.open('rb') as f:
    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
   if h.hexdigest()==digest:found[name]=str(p)
 return found

def upload(dataset,engineering=False):
 contract=check_policy();root=Path(dataset).resolve();receipt=verify_acceptance(root,engineering=engineering)
 namespace=contract['handoff']['engineering_namespace' if engineering else 'formal_namespace']
 remote_root=Path(contract['destination']['root'])
 if str(remote_root)!=REMOTE_ROOT:raise ValueError('Approved remote root mismatch')
 dest=remote_root/namespace/receipt['dataset_id']
 expected=dict(receipt['file_sha256']);expected['dataset-acceptance.json']=sha(root/'dataset-acceptance.json')
 probe='import json\n'+inspect.getsource(reusable_files)+'\nprint(json.dumps(reusable_files('+repr(str(dest))+','+repr(expected)+','+repr(REMOTE_ROOT)+')))\n'
 reusable=json.loads(run(['python3','-B','-c',probe],capture_output=True,text=True,timeout=45).stdout)
 if not set(reusable)<=set(expected):raise ValueError('Unexpected remote reuse inventory')
 # Snapshot missing accepted bytes locally; reverify before streaming.

 with tempfile.TemporaryDirectory(prefix='sonic-handoff-',dir=root.parent) as temporary:
  archive=Path(temporary)/'dataset.tar'
  with tarfile.open(archive,'w') as t:
   for name in sorted(set(expected)-set(reusable)):t.add(root/name,arcname=name,recursive=False)
  verify_acceptance(root,engineering=engineering)
  if sha(root/'dataset-acceptance.json')!=expected['dataset-acceptance.json']:raise ValueError('Acceptance changed during packaging')
  # Verify the tar snapshot too; the source might have changed and changed back.
  with tarfile.open(archive,'r') as t:
   import hashlib
   for member in t:
    h=hashlib.sha256();source=t.extractfile(member)
    for b in iter(lambda:source.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=expected[member.name]:raise ValueError('Snapshot hash mismatch')
  code='import sys,json,os\nfrom pathlib import Path\n'+inspect.getsource(receive_archive)
  code+='\nroot=Path('+repr(REMOTE_ROOT)+').resolve()\ndest=Path('+repr(str(dest))+')\nif not dest.resolve().is_relative_to(root):raise ValueError("Remote path escapes approved root")\n'
  code+='print(json.dumps(receive_archive(sys.stdin.buffer,dest,'+repr(expected)+','+repr(reusable)+')))\n'
  with archive.open('rb') as stream:result=run(['python3','-B','-c',code],stdin=stream,capture_output=True,timeout=300)
 response=json.loads(result.stdout);response.update(engineering_only=engineering,formal_training_started=False,robot_control_started=False,reused_remote_files=len(reusable),transmitted_files=len(expected)-len(reusable))
 if response.get('remote_hash_verification')!='PASS':raise ValueError('Remote hash verification missing')
 return response
