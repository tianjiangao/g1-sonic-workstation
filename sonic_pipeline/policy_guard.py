"""Fail closed when user-fixed workflow documents change unexpectedly."""
import hashlib,json
from pathlib import Path
from sonic_pipeline.settings import HOME,ROOT

def check_policy():
 lock=json.loads((ROOT/'policy-lock.json').read_text())
 for relative,digest in lock['files'].items():
  p=(HOME/relative).resolve()
  if not p.is_relative_to(HOME.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('User-fixed workflow policy changed; stop and request explicit revision: '+relative)
 return json.loads((ROOT/'workflow-contract.json').read_text())

def check_cloud_paths(paths):
 """Formal cloud jobs must stay inside the user-approved deployment root."""
 contract=check_policy();approved=Path(contract['destination']['root']).resolve()
 if HOME.resolve()!=approved:raise ValueError('Formal training must run in the approved remote workspace')
 for value in paths:
  if not Path(value).resolve().is_relative_to(approved):raise ValueError('Formal training path escapes approved workspace: '+str(value))
 return contract

def check_local_paths(paths):
 """Offline dataset products stay in the approved local datasets/reports trees."""
 contract=check_policy();local=contract['local_processing'];base=Path(local['root']).resolve()
 if HOME.resolve()!=base:raise ValueError('This data stage must run on the approved local workstation')
 allowed=[Path(local['datasets']).resolve(),Path(local['engineering_reports']).resolve()]
 for value in paths:
  p=Path(value).resolve()
  if not any(p.is_relative_to(root) for root in allowed):raise ValueError('Local data output escapes approved datasets/reports: '+str(value))
 return contract

def check_processing_output(value,engineering):
 contract=check_local_paths([value]);local=contract['local_processing']
 approved=Path(local['engineering_reports' if engineering else 'datasets']).resolve()
 if not Path(value).resolve().is_relative_to(approved):raise ValueError('Engineering output must stay in reports; formal output must stay in datasets')
 return contract

def check_pinned_files(repo,revision,paths):
 """Compare data-processing files to Git objects, preserving unrelated patches."""
 import subprocess
 repo=Path(repo)
 head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
 if head!=revision:raise ValueError('Official source commit changed: '+str(repo))
 hashes={}
 for name in paths:
  expected=subprocess.check_output(['git','-C',str(repo),'show',revision+':'+name])
  digest=hashlib.sha256(expected).hexdigest();p=repo/name
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Official data source changed: '+str(p))
  hashes[name]=digest
 return hashes

def check_official_sources():
 import subprocess
 from sonic_pipeline.settings import WBC,GROOT
 contract=check_policy()
 data_files=['gear_sonic/data/exporter.py','gear_sonic/data/video_writer.py','gear_sonic/utils/data_collection/transforms.py','gear_sonic/scripts/process_dataset.py']
 wbc=check_pinned_files(WBC,contract['wbc_commit'],data_files)
 files=subprocess.check_output(['git','-C',str(GROOT),'ls-tree','-r','--name-only',contract['groot_commit'],'gr00t','pyproject.toml','uv.lock'],text=True).splitlines()
 if not files:raise ValueError('Pinned GR00T source files missing')
 groot=check_pinned_files(GROOT,contract['groot_commit'],files)
 return {'wbc_commit':contract['wbc_commit'],'groot_commit':contract['groot_commit'],'wbc_files_sha256':wbc,'groot_files_sha256':groot}
