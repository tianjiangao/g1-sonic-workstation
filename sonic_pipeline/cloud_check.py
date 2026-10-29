"""Small cloud CUDA/NCCL preflight; no model or robot interfaces."""
import json,os
import torch
import torch.distributed as dist
rank=int(os.environ.get('LOCAL_RANK',0));world=int(os.environ.get('WORLD_SIZE',1))
if world!=8 or torch.cuda.device_count()!=8:raise RuntimeError('8 visible GPUs and8 torchrun ranks required')
torch.cuda.set_device(rank);p=torch.cuda.get_device_properties(rank)
if p.total_memory<40*1024**3:raise RuntimeError('Insufficient VRAM for this profile')
dist.init_process_group('nccl',device_id=torch.device('cuda',rank))
try:
 x=torch.ones(1,device='cuda');dist.all_reduce(x)
 if x.item()!=8:raise RuntimeError('NCCL all-reduce incorrect')
 if rank==0:print(json.dumps({'cuda_nccl':'PASS','gpus':world,'gpu_name':p.name,'torch':torch.__version__,'vram_gib':p.total_memory/1024**3,'model_loaded':False,'robot_control_started':False}),flush=True)
finally:dist.destroy_process_group()
