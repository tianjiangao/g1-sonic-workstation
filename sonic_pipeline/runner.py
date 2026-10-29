"""Plans and explicitly bounded upstream training. Never starts robot control."""
import json,os,signal,subprocess,time
from pathlib import Path
from sonic_pipeline.manifest import sha
from sonic_pipeline.settings import GROOT,TRAIN_PY,ROOT,BASE_PATH,SCHEMA,HOME,WBC

def env():
 e=os.environ.copy();e.update(PYTHONPATH=str(HOME)+':'+str(WBC)+':'+str(GROOT),HF_HUB_OFFLINE='0',HF_DATASETS_OFFLINE='1',WANDB_MODE='disabled',WANDB_DISABLED='true',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4',NO_ALBUMENTATIONS_UPDATE='1',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
 return e

def gate(dataset,validation=None,smoke=False):
 p=Path(dataset);pro=json.loads((p/'pipeline-provenance.json').read_text());reader=json.loads((p/'reader-validation.json').read_text())
 if pro['schema']!=SCHEMA or reader['actual_gr00t_reader']!='PASS':raise ValueError('Dataset contract not verified by the actual training reader')
 for name,digest in reader.get('artifact_sha256',{}).items():
  f=(p/name).resolve()
  if not f.is_relative_to(p.resolve()) or sha(f)!=digest:raise ValueError('Validated dataset artifacts changed: '+name)
 if not reader.get('artifact_sha256'):raise ValueError('Reader validation lacks dataset artifact hashes')
 if smoke:return pro
 if pro['engineering_only'] or not pro['human_approved']:raise ValueError('Engineering/unreviewed data cannot start formal fine-tuning')
 from sonic_pipeline.acceptance import verify_acceptance
 verify_acceptance(p,engineering=False)
 if not validation:raise ValueError('A separate, human-reviewed validation dataset is required')
 vp=gate(validation,smoke=True)
 if vp.get('engineering_only') or not vp.get('human_approved'):raise ValueError('Validation data not human approved')
 verify_acceptance(validation,engineering=False)
 if any(e.get('split')!='train' for e in pro['episodes']) or any(e.get('split')!='validation' for e in vp['episodes']):raise ValueError('Reviewed split role mismatch: train and validation datasets required')
 train_hashes={json.dumps(e.get('raw_sha256'),sort_keys=True) for e in pro['episodes']}
 val_hashes={json.dumps(e.get('raw_sha256'),sort_keys=True) for e in vp['episodes']}
 train_sources={e['source_episode'] for e in pro['episodes']};val_sources={e['source_episode'] for e in vp['episodes']}
 if train_sources&val_sources:raise ValueError('Train/validation raw-episode overlap')
 if {Path(p).parent.name for p in train_sources}&{Path(p).parent.name for p in val_sources}:raise ValueError('Train/validation recording-session overlap; split entire sessions')
 if train_hashes&val_hashes:raise ValueError('Train/validation raw content overlap')
 return pro

def training_plan(dataset,output,base_model=BASE_PATH,gpus=4,smoke=False,validation=None):
 gate(dataset,validation,smoke)
 if not smoke and (Path(base_model)/'pipeline-engineering-only.json').exists():raise ValueError('Architecture-test checkpoint cannot be used as a pretrained task base')
 if gpus<1:raise ValueError('num_gpus must be positive')
 output=Path(output).resolve()
 if output.exists():raise FileExistsError('Training output already exists; choose a new run directory')
 batch=1 if smoke else gpus*8;steps=1 if smoke else 20000
 entry=GROOT/'gr00t/experiment/launch_finetune.py'
 cmd=[str(TRAIN_PY)]
 if gpus>1:cmd+=['-m','torch.distributed.run','--standalone','--nproc_per_node',str(gpus),'--module','sonic_pipeline.training_entry']
 else:cmd+=['-m','sonic_pipeline.training_entry']
 cmd +=['--base-model-path',str(base_model),'--dataset-path',str(Path(dataset).resolve()),'--embodiment-tag','NEW_EMBODIMENT','--modality-config-path',str(ROOT/'dex1_modality.py'),'--num-gpus',str(gpus),'--output-dir',str(output),'--max-steps',str(steps),'--save-steps','1' if smoke else '5000','--save-total-limit','2' if smoke else '5','--global-batch-size',str(batch),'--dataloader-num-workers','0' if smoke else '4','--num-shards-per-epoch','1' if smoke else '16','--shard-size','128' if smoke else '1024','--no-use-wandb','--no-tune-llm','--no-tune-visual']
 return {'argv':cmd,'cwd':str(GROOT),'output':str(output),'dataset':str(Path(dataset).resolve()),'validation':str(Path(validation).resolve()) if validation else None,'engineering_smoke':smoke,'max_wall_seconds':300 if smoke else None,'training_quality_verified':False,'robot_control_started':False,'runtime_env':{k:env()[k] for k in ['HF_HUB_OFFLINE','WANDB_MODE','OMP_NUM_THREADS']}}

def execute_smoke(plan):
 if plan['argv'][plan['argv'].index('--num-gpus')+1]!='1':raise ValueError('Local bounded smoke is restricted to1 GPU')
 if not plan['engineering_smoke']:raise ValueError('Only bounded engineering training is executable from this helper; use the generated reviewed cloud plan for full training')
 if not plan.get('architecture_only') and not all((Path(plan['argv'][plan['argv'].index('--base-model-path')+1])/name).exists() for name in ['model-00001-of-00002.safetensors','model-00002-of-00002.safetensors']):raise ValueError('Base weights not fully downloaded')
 query=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True,capture_output=True,check=True)
 if int(query.stdout.splitlines()[0])<20000:raise ValueError('Less than20GB GPU free; no other services will be stopped')
 if plan['output'] and Path(plan['output']).exists():raise FileExistsError(plan['output'])
 run=Path(plan['output']);run.mkdir(parents=True);(run/'pipeline-plan.json').write_text(json.dumps(plan,indent=2))
 start=time.monotonic();timed_out=False
 with (run/'training.log').open('w') as log:
  process=subprocess.Popen(plan['argv'],cwd=plan['cwd'],env=env(),stdout=log,stderr=log,start_new_session=True)
  while process.poll() is None:
   if time.monotonic()-start>min(300,plan.get('max_wall_seconds',300)):
    timed_out=True;os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
    break
   time.sleep(1)
 states=list(run.glob('checkpoint-*/trainer_state.json'));steps=0;losses=[]
 for path in states:
  state=json.loads(path.read_text());steps=max(steps,state.get('global_step',0));losses.extend([x.get('loss',x.get('train_loss')) for x in state.get('log_history',[]) if 'loss' in x or 'train_loss' in x])
 import ast,math
 for line in (run/'training.log').read_text(errors='replace').splitlines():
  if line.startswith("{'train_runtime'"):
   metrics=ast.literal_eval(line)
   if math.isfinite(metrics.get('train_loss',float('nan'))):losses.append(metrics['train_loss'])
 report={'exit_code':process.returncode,'timed_out':timed_out,'wall_seconds':time.monotonic()-start,'actual_optimizer_steps':steps,'logged_losses':losses,'smoke_passed':process.returncode==0 and steps>=1 and bool(losses),'engineering_only':True,'task_success_verified':False,'robot_control_started':False,'pretrained_weights_loaded':not plan.get('architecture_only',False)}
 (run/'smoke-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);return report
