#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 ]]; then echo 'Usage: train_8xl40.sh TRAIN_DATASET VALIDATION_DATASET NEW_OUTPUT_DIR' >&2; exit 2; fi
PIPELINE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export G1_PIPELINE_HOME="$PIPELINE_DIR"
export GROOT_ROOT="$PIPELINE_DIR/Isaac-GR00T"
export PYTHONPATH="$PIPELINE_DIR:$GROOT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export WANDB_MODE=disabled
export HF_HUB_OFFLINE=0
export NO_ALBUMENTATIONS_UPDATE=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=4
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
"$GROOT_ROOT/.venv/bin/python" - "$1" "$2" "$3" <<'PY'
import json,os,subprocess,sys
from pathlib import Path
from sonic_pipeline.runner import training_plan,env,gate
from sonic_pipeline.policy_guard import check_cloud_paths
check_cloud_paths(sys.argv[1:])
# Verify immutable local acceptance BEFORE CUDA/resource/model initialization.
gate(sys.argv[1],sys.argv[2],smoke=False)
# Check allocation without creating CUDA contexts on occupied devices.
rows=subprocess.check_output(["nvidia-smi","--query-gpu=name,memory.free","--format=csv,noheader,nounits"],text=True).strip().splitlines()
if len(rows)!=8 or any("L40S" not in row or int(row.rsplit(",",1)[1].strip())<35*1024 for row in rows):raise RuntimeError("Full training requires 8 L40S GPUs with at least 35GiB free each; existing jobs will not be stopped")
import torch
from sonic_pipeline.settings import BASE_PATH,GROOT,TRAIN_PY
if torch.cuda.device_count()!=8:raise RuntimeError('This profile requires8 visible GPUs; adjust the profile after checking actual allocation')
for i in range(8):
 p=torch.cuda.get_device_properties(i)
 if p.total_memory<40*1024**3:raise RuntimeError('Each GPU needs at least40GiB for the default official head/projector fine-tuning profile')
free=[]
for i in range(8):
 with torch.cuda.device(i):free.append(torch.cuda.mem_get_info()[0])
if min(free)<35*1024**3:raise RuntimeError('Less than35GiB free on one or more GPUs; existing jobs will not be stopped')
plan=training_plan(sys.argv[1],sys.argv[3],BASE_PATH,8,False,sys.argv[2]);out=Path(plan['output'])
if not all((BASE_PATH/f'model-{i:05d}-of-00002.safetensors').exists() for i in [1,2]):raise RuntimeError('Base model missing; run download_model.sh')
out.mkdir(parents=True);(out/'pipeline-plan.json').write_text(json.dumps(plan,indent=2))
print(json.dumps(plan,indent=2),flush=True)
# WORLD_SIZE is set by torchrun to8 and agrees with official --num-gpus8.
subprocess.run(plan['argv'],cwd=GROOT,env=env(),check=True)
PY
