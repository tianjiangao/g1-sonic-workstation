from pathlib import Path
import os,json
HOME=Path(os.environ.get('G1_PIPELINE_HOME',str(Path(__file__).resolve().parent.parent)))
_runtime=HOME/'runtime_paths.json'
if _runtime.exists():
 for _key,_value in json.loads(_runtime.read_text()).items():
  if _key not in {'GROOT_ROOT','SONIC_WBC_ROOT','SONIC_RAW_ROOT','UV_CACHE_DIR','HF_HOME','HF_HUB_CACHE','TORCH_HOME','TMPDIR','GR00T_BASE_MODEL','UV_PYTHON_INSTALL_DIR','TRITON_CACHE_DIR','CUDA_CACHE_PATH','TORCH_EXTENSIONS_DIR','XDG_CACHE_HOME'}:raise ValueError('Unknown runtime path field')
  if not Path(_value).resolve().is_relative_to(HOME.resolve()):raise ValueError('Runtime path escapes approved workspace')
  os.environ[_key]=_value
WBC=Path(os.environ.get('SONIC_WBC_ROOT','/opt/g1/GR00T-WholeBodyControl'))
GROOT=Path(os.environ.get('GROOT_ROOT','/opt/g1/Isaac-GR00T'))
DATA_PY=WBC/'.venv_data_collection/bin/python'
TRAIN_PY=GROOT/'.venv/bin/python'
RAW=Path(os.environ.get('SONIC_RAW_ROOT',str(WBC/'outputs/real_sessions/g1_demo')))
ROOT=HOME/'sonic_pipeline'
BASE_REPO='nvidia/GR00T-N1.7-3B'
BASE_REVISION='2fc962b973bccdd5d8ce4f67cc63b264d6886495'
BASE_PATH=Path(os.environ.get('GR00T_BASE_MODEL',str(Path.home()/'.cache/huggingface/hub/models--nvidia--GR00T-N1.7-3B/snapshots'/BASE_REVISION)))
FPS=50
SCHEMA='sonic_token64_dex1x2_v1'
