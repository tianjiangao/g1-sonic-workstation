#!/usr/bin/env bash
set -euo pipefail
cd /opt/g1/workspace
exec /opt/g1/GR00T-WholeBodyControl/.venv_sim/bin/python -m capture.record "$@"
