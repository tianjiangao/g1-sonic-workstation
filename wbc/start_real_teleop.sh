#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
exec python3 -m official_sonic.run_real_teleop "$@"
