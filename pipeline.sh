#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec "${G1_PIPELINE_PYTHON:-python3}" -m sonic_pipeline.cli "$@"
