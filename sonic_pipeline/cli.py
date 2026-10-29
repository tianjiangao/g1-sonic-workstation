"""Local and portable CLI for the official NVIDIA data/posttraining pipeline."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
from sonic_pipeline.settings import *
from sonic_pipeline.manifest import inventory,sha
from sonic_pipeline.runner import training_plan,execute_smoke,env,gate

def call(args,cwd=HOME):
 from sonic_pipeline.local_workflow import call as offline_call
 return offline_call(args)
def main():
 from sonic_pipeline.policy_guard import check_policy
 check_policy()
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='stage',required=True)
 sub.add_parser('status')
 q=sub.add_parser('inventory');q.add_argument('--raw',default=str(RAW));q.add_argument('--output',required=True)
 q=sub.add_parser('prepare');q.add_argument('--manifest');q.add_argument('--split',choices=['train','validation','test'],default='train');q.add_argument('--engineering-episode');q.add_argument('--output',required=True)
 q=sub.add_parser('clean');q.add_argument('--dataset',required=True);q.add_argument('--output',required=True)
 q=sub.add_parser('validate');q.add_argument('--dataset',required=True)
 q=sub.add_parser('train-plan');q.add_argument('--dataset',required=True);q.add_argument('--validation');q.add_argument('--output',required=True);q.add_argument('--base-model',default=str(BASE_PATH));q.add_argument('--gpus',type=int,default=None);q.add_argument('--smoke',action='store_true');q.add_argument('--execute',action='store_true');q.add_argument('--architecture-only',action='store_true')
 q=sub.add_parser('cloud-bundle');q.add_argument('--output',required=True)
 q=sub.add_parser('evaluate-plan');q.add_argument('--dataset',required=True);q.add_argument('--model',required=True);q.add_argument('--output',required=True)
 q=sub.add_parser('review-page');q.add_argument('--manifest',required=True);q.add_argument('--output',required=True)
 q=sub.add_parser('review');q.add_argument('--manifest',required=True);q.add_argument('--output',required=True);q.add_argument('--episode',required=True);q.add_argument('--decision',required=True,choices=['approved','failed','device_test','pending']);q.add_argument('--reviewer',required=True);q.add_argument('--note',required=True);q.add_argument('--split',default='unassigned',choices=['unassigned','train','validation','test']);q.add_argument('--trim-start-s',type=float,default=0.);q.add_argument('--trim-end-s',type=float)
 q=sub.add_parser('local-run');q.add_argument('--manifest');q.add_argument('--engineering-episode');q.add_argument('--split',default='train',choices=['train','validation','test']);q.add_argument('--output',required=True)
 q=sub.add_parser('accept');q.add_argument('--dataset',required=True);q.add_argument('--engineering',action='store_true')
 q=sub.add_parser('upload');q.add_argument('--dataset',required=True);q.add_argument('--engineering',action='store_true');q.add_argument('--receipt-output')
 a=p.parse_args()
 from sonic_pipeline.policy_guard import check_local_paths
 if a.stage in ('inventory','prepare','review-page','review','local-run'):check_local_paths([a.output])
 if a.stage in ('accept','upload','validate'):check_local_paths([a.dataset])
 if a.stage=='clean':check_local_paths([a.dataset,a.output])
 if a.stage in ('prepare','local-run'):
  from sonic_pipeline.policy_guard import check_processing_output
  check_processing_output(a.output,bool(a.engineering_episode))
 if a.stage in ('accept','upload'):
  from sonic_pipeline.policy_guard import check_processing_output
  check_processing_output(a.dataset,a.engineering)
 if a.stage=='upload' and a.receipt_output:
  check_local_paths([a.receipt_output])
  if Path(a.receipt_output).exists():raise FileExistsError(a.receipt_output)

 if a.stage=='status':
  d={'wbc':str(WBC),'groot':str(GROOT),'data_environment_exists':DATA_PY.exists(),'training_environment_exists':TRAIN_PY.exists(),'base_model':str(BASE_PATH),'base_weight_files_complete':all((BASE_PATH/x).exists() for x in ['model-00001-of-00002.safetensors','model-00002-of-00002.safetensors']),'embodiment':'NEW_EMBODIMENT','action_dim':66,'state_dim':34,'fps':FPS,'action_horizon':40,'raw_episodes':len(list(RAW.glob('SESSION_*/episode_*/episode.json'))),'robot_control_started':False,'data_processing_location':'local_workstation','ssh_handoff':'accepted datasets only'};review=ROOT/'review.json';d['human_approved_episode_count']=sum(x['decision']=='approved' for x in json.loads(review.read_text())['episodes']) if review.exists() else None;d['cloud_execution_verified']=(HOME/'reports/cloud-acceptance.json').exists();d['data_environment_verified']=(HOME/'reports/data-environment-ready.json').exists();d['training_environment_verified']=(HOME/'reports/training-environment-ready.json').exists();d['base_hashes_verified']=(HOME/'models/base-model.json').exists();d['base_expected_weight_bytes']=6910499416;d['base_partial_weight_bytes']=sum(x.stat().st_size for x in (ROOT/'downloads').glob('*/*') if x.suffix in ('.part','.tmp'));print(json.dumps(d,ensure_ascii=False,indent=2))
 elif a.stage=='inventory':print(json.dumps(inventory(a.raw,a.output),ensure_ascii=False))
 elif a.stage=='prepare':
  args=[DATA_PY,'-m','sonic_pipeline.convert','--output',a.output,'--split',a.split]
  if a.manifest:args+=['--manifest',a.manifest]
  if a.engineering_episode:args+=['--engineering-episode',a.engineering_episode]
  call(args)
 elif a.stage=='clean':
  from sonic_pipeline.local_workflow import clean
  print(json.dumps(clean(a.dataset,a.output),ensure_ascii=False,indent=2))
 elif a.stage=='validate':call([TRAIN_PY,'-m','sonic_pipeline.validate_dataset','--dataset',a.dataset])
 elif a.stage=='review-page':
  from sonic_pipeline.review_page import build_review_page
  print(json.dumps(build_review_page(a.manifest,a.output),ensure_ascii=False,indent=2))
 elif a.stage=='review':
  from sonic_pipeline.manifest import record_review
  print(json.dumps(record_review(a.manifest,a.output,a.episode,a.decision,a.reviewer,a.note,a.split,a.trim_start_s,a.trim_end_s),ensure_ascii=False,indent=2))
 elif a.stage=='local-run':
  from sonic_pipeline.local_workflow import local_run
  print(json.dumps(local_run(a.output,a.manifest,a.split,a.engineering_episode),ensure_ascii=False,indent=2))
 elif a.stage=='accept':
  from sonic_pipeline.acceptance import accept_dataset
  print(json.dumps(accept_dataset(a.dataset,a.engineering),ensure_ascii=False,indent=2))
 elif a.stage=='upload':
  from sonic_pipeline.upload_dataset import upload
  result=upload(a.dataset,a.engineering)
  if a.receipt_output:
   target=Path(a.receipt_output);target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
  print(json.dumps(result,ensure_ascii=False,indent=2))
 elif a.stage=='train-plan':
  if a.execute:
   from sonic_pipeline.policy_guard import check_cloud_paths
   check_cloud_paths([a.dataset,a.output])
  plan=training_plan(a.dataset,a.output,a.base_model,(a.gpus or (1 if a.smoke else 8)),a.smoke,a.validation)
  if a.architecture_only:
   if not a.smoke:raise ValueError('Architecture-only is an engineering smoke option')
   plan['architecture_only']=True;plan['max_wall_seconds']=240;plan['argv'].append('--skip-weight-loading')
  print(json.dumps(plan,ensure_ascii=False,indent=2))
  if a.execute:
   if not a.smoke:raise ValueError('Full training uses reviewed cloud bundle; this local helper only executes --smoke')
   result=execute_smoke(plan)
   if not result['smoke_passed']:raise SystemExit(2)
 elif a.stage=='cloud-bundle':
  from sonic_pipeline.cloud import bundle
  print(json.dumps(bundle(a.output),ensure_ascii=False,indent=2))
 elif a.stage=='evaluate-plan':
  gate(a.dataset,smoke=True)
  args=[str(TRAIN_PY),'-m','sonic_pipeline.groot_entry','evaluate','--model-path',str(Path(a.model).resolve()),'--dataset-path',str(Path(a.dataset).resolve()),'--embodiment-tag','NEW_EMBODIMENT','--traj-ids','0','--save-plot-path',str(Path(a.output).resolve())]
  print(json.dumps({'argv':args,'cwd':str(GROOT),'env':{'PYTHONPATH':env()['PYTHONPATH'],'HF_HUB_OFFLINE':'1','WANDB_MODE':'disabled'},'metric':'open-loop token/Dex1 prediction error, NOT task success','robot_control_started':False},ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except (ValueError,FileExistsError,FileNotFoundError,subprocess.CalledProcessError) as e:print('PIPELINE BLOCKED: '+str(e),file=sys.stderr);sys.exit(2)
