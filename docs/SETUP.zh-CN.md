# 安装与现场配置

本版本整理于 2026-10-29。它提供可复用源码，不分发官方环境、机器人二进制、模型权重或真实数据。推荐 Ubuntu/Linux；代码中的 `audioop` 需要 Python 3.12 或更早版本。已用现有 Python 3.10 环境验证，不宣称新机器安装验收完成。

## 1. 固定上游

精确版本在 `references/versions.json`。先在独立目录取得官方代码，检查许可证、依赖安装脚本及模型使用条款。不要在已有控制环境里覆盖安装。

```bash
git clone https://github.com/NVlabs/GR00T-WholeBodyControl.git "$HOME/g1-wbc"
git -C "$HOME/g1-wbc" checkout 7f151314d4d1606544bf249d2a7a1cb754c64582
git clone https://github.com/NVIDIA/Isaac-GR00T.git "$HOME/g1-groot"
git -C "$HOME/g1-groot" checkout 51d4c89f72fda44cbf77285c6a8114b52676b8a1
```

按这两个固定 checkout 中的官方安装文档分别建立 `.venv_sim`、`.venv_teleop`、`.venv_data_collection` 及 Isaac-GR00T `.venv`。需要官方子模块与真正的 LFS 资产；LFS 指针不能当 mesh。此步骤可能需要网络、GPU和受许可模型访问，本仓库不自动安装。LeRobot 固定提交 `a445d9c9da6bea99a8972daa4fe1fdd053d711d2`，不要静默换成最新版。

官方[遥操作文档](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vr_wholebody_teleop.html)和[数采文档](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)用于理解组件；在线 main 可能已变化，执行接口以固定 checkout 为准。

## 2. 安装本仓库 overlay

在本仓库根目录执行，四个路径都应由你选择：

```bash
python3 tools/prepare.py --wbc "$HOME/g1-wbc" --workspace "$HOME/g1-workspace" --groot "$HOME/g1-groot" --audio-env "$HOME/g1-audio-env"
# 阅读输出与 patches/wbc-local-fixes.patch 后，用完全相同参数加 --apply
```

默认只读：核对两份 HEAD、WBC 干净状态、目标目录不冲突和补丁可应用。`--apply` 会复制 `capture/`、`sonic_pipeline/` 到新 workspace，复制 `wbc/` 中的 overlay 到 WBC，并应用补丁。文件中的 `/opt/g1/...` 是公开路径标记，将重定位为你提供的路径。工具不会覆写已有 overlay、配置策略、下载依赖、启动相机、SSH 或机器人。安装清单保存在新 workspace 的 `installation.json`；中断时保留现场，先检查它，不盲目重跑。

回滚：只操作本次独立 clone 和新 workspace，先停止自己启动的进程，再将其归档。不得用 `git clean/reset` 清除已有环境或删除原始记录。不要直接把本发布目录覆盖到现有运行项目。

## 3. 现场配置

- 在 `official_sonic/console/backend.py` 的 Config 和启动器参数中检查机器人/工作站地址、DDS 网卡和输出路径。`192.168.123.*` 是参考机器人网段，不保证适合你的现场。
- `official_sonic/profiles/camera-roles.json` 默认未确认。填入自己的序列号，用遮挡法确认物理左右，再记录证据。头部使用稳定设备别名 `/dev/video_head`，不要依赖重启会变化的 `/dev/videoN`。
- `dex1-hardware.json` 中物理左右与 DDS wire 相反是原项目实测结果，不能推定所有 G1 都相同。先做无动作检查；开合验证需自己的现场授权、可靠支撑、旁站和独立急停。发布示例不继承原机开度验收。
- 机器人端相机/控制部署脚本仍含 `/home/unitree/...` 的参考布局。按实际 Orin checkout、TensorRT、环境和容器路径逐项检查。公开源码不保证现场二进制、ONNX 或 systemd 服务已经安装。
- SSH 使用用户已有系统认证。源码支持严格主机密钥校验；不得为方便关闭它。专用密钥路径只是约定，不包含密钥；在自己机器按正常认证流程配置，不复制别人的身份。

## 4. 语音

使用独立 audio 环境中的官方 `unitree_sdk2py.g1.audio`，不要升级身体控制环境来解决音频依赖。CPU 合成环境在 workspace 的 `capture/.venv_voice`，需要 `sherpa-onnx==2.0.1`、`numpy==1.26.4`，另外独立 audio 环境需要 capture 代码和它使用的标准音频依赖。官方 SDK 的来源与当前可用音频接口应先核对；原音频环境 SDK 1.0.1 无可追溯 Git HEAD，已安装关键文件哈希见 `references/audio-sdk.json`，不能假定同版本号任意源码都相同。

`references/voice-model.json` 给出模型下载来源与 SHA-256。自行下载后先核对 archive 哈希，再将文件解压到 `capture/voice/kokoro-int8-multi-lang-v1_1`。创建 `capture/voice/` 后再首次合成；本仓库不含权重或 PCM 缓存。中文男声 sid=58，经 16kHz/mono/s16le 发送。`robot_audio.py` 会把机器人音量设为 100；先阅读这项行为并按现场需要评估。RPC 成功不能替代现场听音。

## 5. 站点策略：正式数据入口默认关闭

`config/workflow-contract.example.json` 仅为脱敏示例，`192.0.2.*` 为文档地址。不会自动创建 `policy-lock.json`，直接执行 pipeline 会因缺锁停止。

站点负责人应在新 workspace 编写和审核自己的 `AGENTS.md`，将示例复制为 `sonic_pipeline/workflow-contract.json`，填写本地 root/datasets/reports、远端账号/两跳路线/根目录，保留审核顺序、维度、固定版本与资源门槛。只有明确批准这份新的站点策略后，才能建立其哈希锁：

```python
# 在你已人工批准的新 workspace 中运行；不是原部署的解锁/绕过命令。
from pathlib import Path
import hashlib, json
root = Path.cwd()
names = ['AGENTS.md', 'sonic_pipeline/workflow-contract.json']
lock = {'schema': 'sonic-policy-lock-v1', 'files': {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}}
with (root/'sonic_pipeline/policy-lock.json').open('x') as f:
    json.dump(lock, f, indent=2)
```

已有部署锁不得通过此片段重新背书。后续策略变更必须由负责人授权、备份旧件与哈希、记录理由。远端训练环境也需要一致、经审核的策略部署；不能仅把本地输出路径改成服务器路径就启动训练。

## 6. 回放模型

`offline_replay` 不包含未明确分发许可的第三方资产。来源、固定 revision、每文件哈希在 `references/dex1-replay-assets.json`。在你审核其使用条件并自行取得对应文件后，保持原相对结构存放在 WBC 的 `offline_replay/vendor/dex1_reference/`，把该清单复制为 `download-manifest.json`。不要执行参考仓库的 builder。

随后用本项目 `python -m offline_replay.build_model --output ...` 在全新目录构建；默认模型目录由 `model_config.json` 指定。构建器使用本机 WBC 官方 G1 XML、mesh 和参考 URDF，核对参考哈希。缺少任何文件时停止，不以 Dex3 模型替代。当前模型源合同也会核对部署输出接口和策略参数文件哈希；不一致需重新审计，不能改哈希凑通过。
