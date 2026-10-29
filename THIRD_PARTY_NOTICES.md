# Third-party notices

This project integrates upstream components; it does not claim authorship of SONIC, Unitree hardware SDKs, pretrained models or third-party robot assets.

| Component | Pinned source / license | Distribution here |
|---|---|---|
| NVIDIA GR00T-WholeBodyControl | `7f151314d4d1606544bf249d2a7a1cb754c64582`; source Apache-2.0, weights under NVIDIA model terms | Modified-source patch plus added adapters; original dual notice retained in `LICENSES/NVIDIA-WBC.txt` |
| NVIDIA Isaac-GR00T | `51d4c89f72fda44cbf77285c6a8114b52676b8a1` | Reference only; not vendored |
| Unitree xr_teleoperate | `817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b`; Apache-2.0 notice | Two exact source files used by Dex1 adapter plus `LICENSE.upstream`; source hashes locked |
| Unitree SDK2 / dex1_1_service | Official user-installed hardware dependencies | Not vendored; inspect their own licenses and required versions |
| Kokoro / sherpa-onnx | Model provenance and SHA in `references/voice-model.json`; Apache-2.0 reported by source manifest | Metadata only; no model archive, weights or generated PCM |
| Community Dex1 replay models/meshes | `lerobot/unitree-g1-mujoco` revision `68459ed68f6f68e1f661091dfcb6ebce44681aec`; model-card license unspecified | Manifest and locally authored builder only; no model/mesh assets redistributed |

Modified NVIDIA source files are explicitly identified by `patches/wbc-local-fixes.patch`. Added adapters and source packaging may replace original site paths with documented examples; see `references/source-manifest.json`. Apache-2.0 for this repository does not grant rights to excluded assets or model weights.

Official sources:

- https://github.com/NVlabs/GR00T-WholeBodyControl
- https://github.com/NVIDIA/Isaac-GR00T
- https://github.com/unitreerobotics/xr_teleoperate
- https://github.com/unitreerobotics/unitree_sdk2_python
- https://github.com/unitreerobotics/dex1_1_service
- https://huggingface.co/lerobot/unitree-g1-mujoco
- https://github.com/k2-fsa/sherpa-onnx

Original training/partner slides, private documents, recordings, operator images and server run logs are intentionally excluded. Source publication does not license those materials.
