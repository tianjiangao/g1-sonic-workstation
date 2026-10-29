# Validation and acceptance boundaries

Original-site offline regression, run for this publication on 2026-10-29:

| Command / environment | Result |
|---|---|
| WBC `.venv_sim/bin/python -m unittest discover -s capture/tests -v` from original workspace | 42 passed |
| WBC `.venv_data_collection/bin/python -m unittest discover -s sonic_pipeline/tests -v` from original workspace | 42 passed |
| `PYTHONPATH=external_dependencies/unitree_sdk2_python .venv_sim/bin/python -m unittest discover -s official_sonic/console/tests -v` from original WBC | 116 run, 1 skipped, remaining passed |

These results cover the existing commissioned source layout. They are not a new-machine installation result or a hardware acceptance claim. Logs remain in the private local publication report; no telemetry or recordings are published.

Release checks and exact commands are recorded in `references/release-checks.json` after they run. To reproduce the hardware-independent subset from this repository:

```bash
python3 -m unittest discover -s tests -v
# Choose an existing environment with numpy, OpenCV, msgpack and pyzmq:
PYTHONPATH=wbc:. /path/to/python -m unittest discover -s capture/tests -v
python3 -m compileall -q capture sonic_pipeline wbc tools tests
```

The source overlays are expected to be installed into a pinned WBC checkout for their tests. Pipeline tests that read site policy cannot run unconfigured: no real deployment lock is distributed. `pipeline.sh status` also checks policy before argument parsing and intentionally stops until the site's own approved lock exists.

Original-site passive replay checks can be repeated after obtaining and building the required licensed model assets, using the instructions in `docs/reference/offline_replay-README.zh-CN.md`. Do not claim those model-dependent tests passed on this source-only release.

Not performed as part of publication: real robot motion, gripper mechanics, new audible playback, strict sensor clock sync, reboot/cold-start acceptance, formal training, independent task-success evaluation or dynamics/contact validation. A trained/deployable policy and new-machine acceptance are not delivered by this release.

Release installation smoke: source prepared into a separate clean checkout at the pinned commit, then 116 console tests (1 skip) and 42 capture tests (1 optional voice skip) passed with that installed overlay and the existing dependency environments. Four display-only gripper mapping tests and six packaging helper tests passed. This verifies source relocation/patching and offline behavior, not dependency installation on a fresh computer. The initial failed source-release run is preserved in the release check summary.
