#!/usr/bin/env bash
set -euo pipefail
PIPELINE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
"$PIPELINE_DIR/Isaac-GR00T/.venv/bin/python" - <<'PY'
from huggingface_hub import snapshot_download
from pathlib import Path
import hashlib
base=Path(snapshot_download('nvidia/GR00T-N1.7-3B',revision='2fc962b973bccdd5d8ce4f67cc63b264d6886495',token=False,allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.jinja','*.yaml','*.yml']))
expected={'model-00001-of-00002.safetensors':'8a1a1d8a33c99103c7c80c136073c5bb8bfe9ca8f7a970c93c033ea89742906d','model-00002-of-00002.safetensors':'c3f61940deb2007ba1ad7743013b57f0f8462356151db9655175d7aca2d40661'}
for name,digest in expected.items():
 h=hashlib.sha256()
 with (base/name).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 if h.hexdigest()!=digest:raise RuntimeError('Model SHA256 mismatch: '+name)
print('Verified model:',base)
# Only tokenizer/configuration assets are needed in addition to the full GR00T checkpoint.
print(snapshot_download('nvidia/Cosmos-Reason2-2B',revision='9ce19a195e423419c349abfc86fd07178b230561',token=False,allow_patterns=['*.json','*.txt','*.model','*.jinja']))
PY
