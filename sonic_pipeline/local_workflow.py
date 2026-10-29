"""Offline orchestration of pinned conversion, official cleaning and acceptance."""
import json,subprocess
from pathlib import Path
from sonic_pipeline.settings import DATA_PY,TRAIN_PY,WBC,HOME,SCHEMA
from sonic_pipeline.manifest import sha
from sonic_pipeline.runner import env
from sonic_pipeline.policy_guard import check_local_paths,check_processing_output,check_official_sources

def call(argv):
 environment=env();environment.update(CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
 return subprocess.run([str(x) for x in argv],cwd=HOME,env=environment,check=True)

def clean(dataset,output):
 src=Path(dataset).resolve();dest=Path(output).resolve();check_local_paths([src,dest])
 if dest.exists():raise FileExistsError('Clean output exists; never clean in place')
 if dest==src or src in dest.parents:raise ValueError('Clean output must be outside source dataset')
 pro=json.loads((src/'pipeline-provenance.json').read_text())
 if pro['schema']!=SCHEMA:raise ValueError('Wrong input schema')
 from sonic_pipeline.acceptance import file_inventory
 check_processing_output(dest,pro['engineering_only'])
 source_versions=check_official_sources()
 before=file_inventory(src)
 processor=WBC/'gear_sonic/scripts/process_dataset.py'
 call([DATA_PY,processor,'--dataset-path',src,'--output-path',dest,'--no-remove-stale-smpl'])
 if file_inventory(src)!=before:raise ValueError('Official processing changed source dataset')
 pro['official_cleaning']={'source_dataset':str(src),'smpl_cleaning_disabled':True,'source_provenance_sha256':sha(src/'pipeline-provenance.json'),'source_files_sha256':before,'processor_sha256':sha(processor),'processing_location':'local_workstation','official_source_versions':source_versions}
 (dest/'pipeline-provenance.json').write_text(json.dumps(pro,ensure_ascii=False,indent=2))
 if (src/'human-review.json').exists():(dest/'human-review.json').write_bytes((src/'human-review.json').read_bytes())
 call([TRAIN_PY,'-m','sonic_pipeline.validate_dataset','--dataset',dest])
 return {'cleaned':str(dest),'engineering_only':pro['engineering_only']}

def local_run(output,manifest=None,split='train',engineering_episode=None):
 check_processing_output(output,bool(engineering_episode))
 if bool(manifest)==bool(engineering_episode):raise ValueError('Choose reviewed manifest OR engineering episode')
 root=Path(output)
 if root.exists():raise FileExistsError(root)
 root.mkdir(parents=True);args=[DATA_PY,'-m','sonic_pipeline.convert','--output',root/'converted','--split',split]
 if manifest:args+=['--manifest',manifest]
 else:args+=['--engineering-episode',engineering_episode]
 # Logs and partial outputs stay available if any subprocess fails.
 (root/'run-request.json').write_text(json.dumps({'manifest':str(manifest) if manifest else None,'engineering_episode':str(engineering_episode) if engineering_episode else None,'split':split,'engineering_only':bool(engineering_episode),'robot_control_started':False},indent=2))
 with (root/'conversion.log').open('w') as log:
  environment=env();environment.update(CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
  subprocess.run([str(x) for x in args],cwd=HOME,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True)
 clean(root/'converted',root/'cleaned')
 from sonic_pipeline.acceptance import accept_dataset
 receipt=accept_dataset(root/'cleaned',engineering=bool(engineering_episode))
 result={'output':str(root.resolve()),'accepted_dataset':str((root/'cleaned').resolve()),'dataset_id':receipt['dataset_id'],'engineering_only':receipt['engineering_only'],'formal_training_eligible':receipt['formal_training_eligible'],'robot_control_started':False,'uploaded':False}
 (root/'run-result.json').write_text(json.dumps(result,indent=2));return result
