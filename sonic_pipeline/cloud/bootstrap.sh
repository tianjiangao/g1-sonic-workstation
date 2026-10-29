#!/usr/bin/env bash
set -euo pipefail
PIPELINE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PIPELINE_DIR"
sha256sum -c SHA256SUMS
if [[ -e Isaac-GR00T ]]; then
  echo 'Isaac-GR00T already exists; refusing to overwrite it. Use a fresh deployment folder.' >&2
  exit 2
fi
mkdir Isaac-GR00T
tar -xf Isaac-GR00T-source.tar -C Isaac-GR00T
command -v uv >/dev/null || { echo 'Install uv==0.12.16 from reviewed PyPI wheel first.' >&2; exit 2; }
cd Isaac-GR00T
# Pinned official lock file and reviewed repository sources; no remote shell installer.
uv sync --frozen --all-extras
.venv/bin/python -c 'import torch,transformers,gr00t; print(torch.__version__,torch.cuda.device_count()); assert torch.cuda.is_available()'
printf '\nEnvironment installed. Run download_model.sh, then train_8xl40.sh with reviewed datasets.\n'
