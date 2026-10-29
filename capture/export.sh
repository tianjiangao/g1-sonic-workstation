#!/usr/bin/env bash
set -euo pipefail
cd /opt/g1/workspace
exec /opt/g1/GR00T-WholeBodyControl/.venv_data_collection/bin/python -m capture.export "$@"
