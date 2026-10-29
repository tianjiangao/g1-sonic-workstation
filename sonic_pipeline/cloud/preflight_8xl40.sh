#!/usr/bin/env bash
set -euo pipefail
PIPELINE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export G1_PIPELINE_HOME="$PIPELINE_DIR"
export GROOT_ROOT="$PIPELINE_DIR/Isaac-GR00T"
export PYTHONPATH="$PIPELINE_DIR:$GROOT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$GROOT_ROOT/.venv/bin/python" -m torch.distributed.run --standalone --nproc_per_node 8 --module sonic_pipeline.cloud_check
