> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# SONIC + Dex1：手柄夹取、遥操作数采与数据清洗复现说明

交接日期：2026-10-27（Asia/Shanghai）。对象：同事及其电脑上的 Codex。

本文件根据当前工作站源码、版本锁与已有报告整理。目标是让双方复现同一套实现、用同一套证据同步进度。本文是操作和交接说明，不修改既有 AGENTS.md 或锁文件，不授权自动启动机器人。本次编写只检查本机文件及离线命令，没有运行真机、上传数据或启动训练。

## 1. 先读这一页：我们做到了什么

使用 PICO 手柄与全身追踪输入，NVIDIA SONIC 控制 G1 身体；左右食指 Trigger 经适配器控制左右 Dex1 单自由度夹爪。工作站被动订阅身体、夹爪与三路相机，保存原始事件和图像。之后在工作站人工回放，恢复真实 SONIC token，使用官方工具导出、清洗、回读并验收；验收后的数据才允许传到远端。

```text
PICO / XRoboToolkit → 工作站输入适配 → SONIC Manager → Orin 原版 SONIC → G1 身体
                        └→ Trigger 适配 → Unitree 官方 Dex1 循环 → Orin 串口服务 → 夹爪
身体反馈 + token + Dex1状态/命令 + 头/左腕/右腕图像
    → 工作站原始录制 → 人工回放审核 → 50Hz as-of token转换
    → Gr00tDataExporter → process_dataset.py → 真实GR00T读取器 → 哈希验收
    → 两跳SSH交付 → 远端训练（独立门禁）
```

截至本次检查，必须按下面的层次描述进度：

| 项目 | 已有证据与边界 |
|---|---|
| 真机手臂、夹爪响应 | 有前轮操作者确认与日志；不等于每个修改版本、机械全行程或完整抓取任务均已验收 |
| 夹爪连续性/失联保护 | 有隔离 DDS / 模拟反馈验证；更换电脑、驱动、映射后需重新检查 |
| 原始试录 | 默认 SONIC raw 根目录下有9条 episode；不能把“完整保存”当成“抓取成功” |
| 正式人工审核 | 当前 pipeline status 的 approved 数为0；本次没有批准任何片段 |
| 转换、清洗、GR00T回读 | 有 engineering_only 工程验证：1141个50Hz采样点、三路各1141帧、state 1×34 / action 40×66；不是正式任务数据 |
| 数据交付 | 有较早工程包的远端哈希收据；后续另一工程包上传日志超时，不能把旧收据当成新包成功 |
| 正式训练/任务成功 | 本机基座两分片文件尚不齐全，正式数据尚未审核完成；本次未验证远端资源、训练或任务成功 |

**文档不等于完整软件包。** 仅克隆官方仓库无法得到我们新增的数采器、Dex1适配与工作台；要同时交接第4节列出的本地源码、补丁、锁与许可。虚拟环境不能简单跨机器复制后假定可运行。

## 2. 用了什么：硬件、软件、环境

### 硬件与分工

| 组件 | 当前用途 |
|---|---|
| Ubuntu 22.04.5 工作站 | PICO输入、GUI、Dex1桥接、被动录制、人工审核、转换、清洗与验收 |
| PICO 头显、左右手柄及现有全身追踪设备 | 提供姿态、模式键、Trigger输入；APK/固件/Tracker组合版本需在同事现场补录，本文没有假定兼容 |
| G1 + 机载 Orin | 原版 SONIC 身体推理与控制、相机服务、Dex1串口服务 |
| 左右 Dex1 | 各1自由度；记录真实 q，单位 rad |
| 头部 UVC 双目 | 原始1280×480；正式转换取左目640×480，原始双目不改 |
| 左右腕相机 | 两路640×480；按物理左右确认，不凭设备枚举顺序 |
| 远端训练机 | 仅接收已验收包；正式训练目标8×L40S，每卡至少35GiB空闲 |

### 固定上游版本

| 项目 | 来源 / 锁定值 |
|---|---|
| SONIC / GR00T-WholeBodyControl | https://github.com/NVlabs/GR00T-WholeBodyControl ，commit `7f151314d4d1606544bf249d2a7a1cb754c64582` |
| Isaac-GR00T | https://github.com/NVIDIA/Isaac-GR00T ，commit `51d4c89f72fda44cbf77285c6a8114b52676b8a1` |
| Unitree Dex1 控制循环 | xr_teleoperate commit `817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b`；只复用获准Dex1相关代码，不接入其录制/训练流程 |
| Dex1串口服务 | 既有说明记录 `ced3216290bb22dae356213993786beeaa7143ab` 及获准初始化修复；本次未登录Orin重新验证 |
| 后训练基座 | `nvidia/GR00T-N1.7-3B` revision `2fc962b973bccdd5d8ce4f67cc63b264d6886495` |
| Backbone revision | contract锁定 `9ce19a195e423419c349abfc86fd07178b230561` |

工作站 WBC 仓库存在未提交修改，包括相机、PICO reader/manager、旋转转换、仿真与部署相关文件；Isaac-GR00T本次 tracked工作区检查为空。**commit相同并不代表运行代码相同**，要额外交接工作区差异和新增文件。不要丢弃、reset或自动覆盖这些修改。

### Python环境与本次读取到的关键包元数据

环境表是本机快照，不是完整安装锁；重建时仍需原锁文件、源码来源、原生库与兼容性检查。

| 目录 | Python / 关键包 | 分工 |
|---|---|---|
| WBC `.venv_teleop` | Python3.10；xrobotoolkit-sdk1.0.2、numpy1.26.4、pyzmq27.2.0、torch2.14.1 | PICO / 输入流 |
| WBC `.venv_sim` | Python3.10；numpy1.26.4、opencv4.11.0.86、pyzmq27.2.0、unitree-sdk2py1.0.1、torch2.14.0 | Dex1桥、原始录制、隔离验证 |
| WBC `.venv_data_collection` | Python3.10；lerobot0.1.0、torch2.6.0+cpu、av17.1.0、pyarrow25.0.1、numpy1.26.4 | 官方Exporter与清洗 |
| Isaac-GR00T `.venv` | Python3.12；gr00t0.1.0、torch2.9.0+cu128、pyarrow23.0.1、numpy1.26.4 | 真实训练读取器；离线验证屏蔽CUDA |
| G1 `capture/.venv_voice` | manifest锁定sherpa-onnx2.0.1、numpy1.26.4，Kokoro v1.1中文int8、CPU两线程 | 本地语音生成 |
| `/opt/g1/audio-env` | 现有独立SDK环境；不用于本流程的录制/训练 | 仅G1 AudioClient扬声器接口 |

语音当前路径：`capture/pcm.py → neural_voice.py → robot_audio.py → AudioClient.PlayStream`，16kHz单声道s16le，男声zm_009/sid58。模型来源、许可证Apache-2.0及下载包SHA256见 `capture/voice/manifest.json`。该包SHA256为 `259c9c8bc906d6078e4e0570421885dabb68b539c2f970fcbb890a58eeaf3e9c`。当前助手会设置音量100；复现前现场确认是否允许。RPC成功不证明实际可听；语音失败应报告，不伪装采集成功。

## 3. 网络与硬件映射：必须逐项核对

以下为原工作站配置。换电脑时先形成差异表，不自动改网卡、不直接套用别人的串口与序列号。

| 端点/设备 | 当前值 | 作用 |
|---|---|---|
| 工作站机器人网卡 | `enp4s0` | Unitree DDS |
| 工作站PICO/Manager地址 | `192.168.123.99` | 远端SONIC回连的输入地址 |
| Orin | `192.168.123.164` | 身体与相机服务；与训练服务器不是同一主机 |
| XRoboToolkit PC Service | 本机SDK端口60061 | 端口可达不等于有效全身输入 |
| ZMQ 5556 | 工作站 | PICO / manager / planner等输入 |
| ZMQ 5558 | 工作站，本地桥默认连127.0.0.1 | `dex1_trigger`；桥接输入，不能据默认回环连接推定发布端只绑定回环 |
| ZMQ 5557 | Orin | `g1_debug`、robot_config等反馈与真实token |
| ZMQ 5555 | Orin | SONIC `ImageMessageSchema`三路图像 |
| DDS夹爪 | `rt/dex1/{left,right}/{cmd,state}` | 话题左右必须通过profile还原到物理左右 |

当前相机是SONIC 5555协议；旧文档里的55555/55556/55557不能直接用于当前录制器。配置发布频率15Hz，历史实测聚合约10Hz；既不承诺50Hz曝光，也不承诺传感器时钟同步。

**本机已确认的Dex1路由：物理左 → wire right；物理右 → wire left。** 本机profile记录物理左motor ID0、`/dev/ttyUSB2`，物理右motor ID1、`/dev/ttyUSB1`。这是当前接线结果，不是所有G1通用规定。桥接和录制必须读取同一映射，不要二次交换左右。

当前左腕序列号 `LEFT_CAMERA_SERIAL`，右腕 `RIGHT_CAMERA_SERIAL`；头部别名 `/dev/video_head`。不同机器人必须重新核对遮挡画面与物理侧，不能照抄这些序列号后就标confirmed。

## 4. 同事需要拿到哪些文件

原机目录约定：

```text
/opt/g1/workspace/
  AGENTS.md
  pipeline.sh
  capture/                  # 原始录制、图像适配、语音、旧诊断导出、测试
  sonic_pipeline/           # 审核、token转换、官方清洗、读取、验收、上传
  datasets/reviews/         # 审核清单，逐版追加
  datasets/<新版本>/        # 正式转换/清洗结果
  reports/                  # engineering_only与失败证据
  recordings/               # 既有原始数据，禁止擅自移动/删除
/opt/g1/GR00T-WholeBodyControl/
  official_sonic/           # 工作台、输入适配、Dex1桥、vendor、profiles与许可证
  sim_teleop/               # 仿真隔离、安全工具及其依赖
  start_real_teleop.sh
  start_sim_teleop.sh
  gear_sonic/               # 固定官方源码 + 已审核本机补丁
  gear_sonic_deploy/        # 部署配置/模型；不能跨架构直接复制二进制
  outputs/real_sessions/g1_demo/SESSION_*/episode_*/
/opt/g1/Isaac-GR00T/
```

源码交接应包含：上述项目源码、上游commit、tracked差异、新增文件白名单、依赖锁/完整包版本清单、SDK/PC Service/头显版本、vendor LICENSE、模型清单与哈希、硬件映射证据。本文附录给出关键文件指纹；完整交接包需另生成全量哈希清单。

不把 `.ssh`、私钥、密码、token、认证缓存/socket、无关用户项目、整个home目录或未经批准的原始影像打包。原始样本若需交接，只用已结束且获准共享的完整episode，保留来源与SHA256，不能只拿 `frames.jsonl` 丢掉token所在事件日志。模型按既有授权和许可交付，不自动下载。本文未生成或发送源码包。

### 换电脑的路径门禁

当前 `workflow-contract.json` 将本机数据处理根锁定为 `/opt/g1/workspace`，`capture/start.sh`、工作台CAPTURE_HOME、语音辅助环境等也含绝对路径；Dex1桥真机网卡同样固定。只改环境变量不能完成迁移。

- 若同事环境确实使用同一批准路径及硬件配置，保留原锁并校验；路径相同仍须检查版本和设备。
- 若用户名、根目录、网卡、硬件或远端目标不同，先产出迁移差异与补丁草案。受保护文件的修订需由用户明确授权，再备份原件与哈希，记录理由，并一致更新引用和锁；不得为让检查通过而改锁。
- 不用符号链接伪装已验收目录，不降低质量门槛，不静默换SDK/驱动/模型。
- 安装前检查已有环境；缺失依赖按锁定来源与版本重建独立环境，记录许可证与回滚。本文没有提供一条盲装全依赖的命令，因为当前定制代码与原生依赖尚不能由单个requirements完整描述。

## 5. 第一阶段：先复现离线工程，禁止先启控

先让Codex读取本文件及AGENTS，检查Git、版本、锁、文件哈希、解释器与依赖。原机可执行的检查命令如下；同事需先解决第4节路径问题。

```bash
cd /opt/g1/workspace
./pipeline.sh status
./pipeline.sh local-run --help
./pipeline.sh review --help
python3 -B -c 'from sonic_pipeline.policy_guard import check_policy,check_official_sources; check_policy(); check_official_sources(); print("policy and pinned sources PASS")'
```

这些检查不启动身体/Dex1控制器，不等于环境功能已全部通过。status里的某些verified字段由特定报告路径是否存在得出，不能单独当完整验收。不要把 `official_sonic.run_real_teleop --check-only` 当纯本地检查：它会SSH并执行运行容器准备，虽不启身体控制，也有环境准备副作用。

离线测试命令（同事复现时运行；本次文档编写没有重跑整套测试）：

```bash
cd /opt/g1/workspace
/opt/g1/GR00T-WholeBodyControl/.venv_sim/bin/python -m unittest discover -s capture/tests -v
python3 -m unittest discover -s sonic_pipeline/tests -p 'test_*.py' -v
```

需要工程端到端时，选择获准共享、完整且包含真实token的试录，以新目录运行：

```bash
./pipeline.sh local-run \
  --engineering-episode '/实际完整session/episode_000000' \
  --output '/opt/g1/workspace/reports/NEW_ENGINEERING_ONLY'
```

验收：converted/cleaned和日志产生；reader验证真实执行；state/action维度正确；三视频与表格帧数一致；收据明确engineering_only=true、formal_training_eligible=false。缺数据/时序/依赖应如实失败，不生成假动作、补零手指或换29D动作绕过。

## 6. 第二阶段：现场手柄夹取与遥操作录制

本节仅供有具体现场授权的操作者执行。可靠支撑、清场、旁站和独立急停必须可用；同一机器人不能由两台电脑同时启控。远程同事复现优先用离线样本，不擅自接管正在运行的机器人。

### 启动与录制

1. 启动已配套的XRoboToolkit头显客户端与PC Service；Full Body/Send开启，Switch w/ A Button关闭。确认有效全身输入，而非只看服务端口。
2. 打开桌面“SONIC 工作站”；等价界面入口为：

   ```bash
   python3 /opt/g1/GR00T-WholeBodyControl/official_sonic/console/app.py
   ```

3. 核对“采集设置”：robot/camera/streamer地址、任务文字、dataset名称、输出根与15Hz频率。工作台默认保存到WBC的 `outputs/real_sessions/<dataset>/`；独立录制器默认保存到G1的 `recordings/`，不要因找不到数据就重复采集。
4. 若遥操未运行，由现场操作者点击“启动遥操与数采（启动后需点开始采集）”，完成现场确认。该入口会先等有效PICO数据，再检查相机、运控交接和DDS控制权，必要时准备容器及Dex1服务，随后启动原版SONIC与录制器。**INIT本身会带力**。不要绕过检查直接加 `--operator-start`。
5. 若遥操已运行，只点击“仅启动数采（遥操已运行）”；单实例锁若报告已有数采器，使用原实例。
6. 等 `Init Done` 再按已批准的标定/模式键；等工作台“数据就绪”后点击“开始采集”。启动系统不会自动开始episode。
7. 完成一次完整任务：接近→夹取→搬运→释放→稳定结束。点击“结束并保存”，确认实际文件完整落盘、路径与条数更新。中断或缺流时不能当有效成功数据。
8. 保存后再按现场SONIC流程停止身体。退出录制器不停止机器人；工作台停止只管理自己启动的作业，不替代独立急停。

### 常用按键

| 按键 | 当前含义 | 边界 |
|---|---|---|
| 左/右食指Trigger | 对应机器人自身左/右Dex1；按压闭合，松开回本轮启动开度 | 不是侧面Grip；不保证自动张到机械全开 |
| ABXY同时一次 | Init Done后启策略/初次标定进PLANNER；运行时请求停止并退出 | 软件停止，不是独立急停；按后全部松开 |
| A+X | PLANNER ↔ POSE | 切入前姿态对齐；不要与ABXY混淆 |
| 左Grip+A | 当前episode开始/停止录制 | 需录制器运行且数据有效；建议一轮选GUI或手柄一种，避免重复切换 |
| 左Grip+B | 标记discarded并结束该条 | 保留原文件，不等于删除 |
| B+Y / 菜单键 / 摘头显 | 不能作为通用整机急停 | 冻结上半身仍可能有下肢/夹爪控制；菜单暂停还可能让夹爪停发 |

PLANNER的IDLE与Slow Walk是另一层运动模式。规划走路涉及AB选择模式及摇杆输入，不属于本交接的默认复现动作；悬挂时不执行地面走路，不尝试跑跳等未验收模式。更完整按键解释见WBC `official_sonic/PICO按键速查.zh-CN.md`，仍需结合当前源码核对。

### 夹爪具体怎样实现

`streamer.py`从同一接受的PICO快照提取左右Trigger；`dex1_bridge.py`订阅Trigger、manager_state及g1_debug。`dex1_mapping.py`检查数值、序号与新鲜度，再输入固定的Unitree Dex1官方控制循环。该循环与滤波类加载前校验vendor SHA256，适配层接管启动、状态注入与发布边界，避免上游构造函数立即发布。

输入Trigger范围0～1。每侧启动时捕获真实开度q_open，映射为：

```text
pinch = 5 + 2 × (q_open / 5.4) × (1 - trigger)
官方标度：pinch 5 → q目标0；pinch 7 → q目标5.4rad
```

这说明命令标度，不是机械零点/完整行程标定。两侧扳机先释放至少0.25s；每侧首次主动按压超过0.1才激活，未激活侧不自动全开。官方Kp=5、Kd=0.05、滤波和每步0.18rad限幅保持。当前默认未启用额外试验0.15rad余量/0.5rad/s限速；仅 `--commissioning-limits` 显式启用，不自行改默认以“优化”。

PICO、模式、策略反馈与左右Dex1状态过期约250ms会停发并锁定退出，需要处理故障后重新启动夹爪桥；不会自动恢复。夹爪桥或录制器失败时，监督器可记录降级但身体会话继续，**夹爪停止不等于整机已停**。Dex1串口服务既有约1s无命令BRAKE逻辑，停发不等于250ms内断电。

### 独立录制器：仅在已有授权控制链运行时使用

```bash
/opt/g1/workspace/capture/start.sh --task '抓取并放置杯子'
```

就绪后在该录制器终端输入 `s` 回车开始，再输入 `s` 回车保存，`q`或Ctrl+C只退出录制器。带 `--probe --seconds 15` 可被动检查输入而不建episode，可能写探测记录；本次未执行实时探测。它仍连接现有网络流，不能当成完全离线测试。`--no-dds`不能完成Dex1就绪验收。

## 7. 原始记录里有什么，为什么能恢复正式动作

每条episode保存：`episode.json`、`context.json`、`frames.jsonl`、`events.jsonl`及按内容哈希命名的JPEG；session还记录配置与状态。`complete=true`仅代表录制完整，不代表任务成功。

`frames.jsonl`是默认15Hz诊断采样；高频事件和启动context保留g1_debug真实 `token_state(64)`、body_q、姿态、robot_config、manager、左右Dex1反馈与命令、相机接收等。只复制诊断帧或旧导出，会失去正式转换所需的事件上下文。

`capture/export.sh`以及工作台“导出最近保存段”仍属旧 `g1_29_dex1` 诊断格式。它的29D身体命令不能冒充64D SONIC token；正式训练用下一节 `pipeline.sh local-run`。

新鲜度约束：身体/模式/Dex1命令反馈0.25s、相机0.5s、配置30s。错误维度、NaN/Inf、时序异常、损坏图像、回调溢出和低磁盘等会阻止开始或使当前段不完整。恢复后不自动续录；保留失败原件。

## 8. 第三阶段：人工回放、审核与集合划分

下面命令在批准的原机目录执行，所有新输出必须不存在；重复运行换版本名，不能删原始记录“重来”。

```bash
cd /opt/g1/workspace
./pipeline.sh inventory \
  --raw /opt/g1/GR00T-WholeBodyControl/outputs/real_sessions/g1_demo \
  --output /opt/g1/workspace/datasets/reviews/colleague_v001_inventory.json
./pipeline.sh review-page \
  --manifest /opt/g1/workspace/datasets/reviews/colleague_v001_inventory.json \
  --output /opt/g1/workspace/reports/colleague_v001_review
```

浏览器打开输出 `index.html`，回放头部双目与左右腕，检查Dex1命令/反馈。页面只展示，不自动写审核决定。审核人核对目标、接近/抓住/搬运/释放、掉落碰撞、视野、左右语义与任务文字。

对设备测试的审核示例：

```bash
./pipeline.sh review \
  --manifest /opt/g1/workspace/datasets/reviews/colleague_v001_inventory.json \
  --output /opt/g1/workspace/datasets/reviews/colleague_v002_reviewed.json \
  --episode '/实际session绝对路径/episode_000000' \
  --decision device_test --reviewer '实际审核人' \
  --note '实际回放观察与判定原因' --split unassigned
```

人工确认任务成功后才可以将该次决定设为approved，并指定train/validation/test；未看过不能代签。支持failed/device_test/pending；每次以上一版清单为输入写新版本，保留历史。裁剪用 `--trim-start-s` / `--trim-end-s` 秒边界，不改原件。

**按完整SESSION划分集合**：同session的episode不能分散到train与validation/test，相邻切片不能跨集合；还要防止复制相同原始内容造成泄漏。至少需要独立人工审核验证session。旧审计发现第9条夹爪命令几乎恒定，不能凭时长或结构正确判为成功夹取。

## 9. 第四阶段：真实token转换、官方清洗、数据验收

已有人工批准清单时执行：

```bash
./pipeline.sh local-run \
  --manifest /opt/g1/workspace/datasets/reviews/colleague_v003_approved.json \
  --split train --output /opt/g1/workspace/datasets/colleague_task_v001_train
./pipeline.sh local-run \
  --manifest /opt/g1/workspace/datasets/reviews/colleague_v003_approved.json \
  --split validation --output /opt/g1/workspace/datasets/colleague_task_v001_validation
```

这里的v003是占位清单，必须由实际人工审核步骤生成；不存在或没有approved时失败是正确结果，不能复制示例伪造审核。

实际实现顺序：

1. 校验规范、固定上游数据源码、源episode完整性与指纹、审核人/任务/split；配置不同的token控制器不合并。
2. `convert.py`用工作站接收monotonic时间建立50Hz网格。对每个采样时刻只选该时刻或以前最近的事件（as-of），不读未来帧、不插值伪造token；缺失或过期必需流失败。每条至少41个网格点，满足40步动作窗口的检查要求。
3. 使用官方 `Gr00tDataExporter`写全新 `converted/`。状态=29D body_q + 左右Dex1反馈各1D + 3D projected gravity，共34D；动作=真实64D token_state + 左右Dex1命令各1D，共66D，窗口40×66。Dex1观测与命令不可互换。
4. 原始双目保留；正式头部图像取左目640×480，腕图像保留物理左右，按Exporter所需颜色格式写入。视频与表格共享同一采样网格。
5. `local_workflow.clean`调用固定官方 `gear_sonic/scripts/process_dataset.py --no-remove-stale-smpl` 写全新 `cleaned/`。VR3PT/Dex1不能按零SMPL误删；脚本不判断任务是否成功。不在此处混用unitree_lerobot/TeleImager。
6. 全量扫描低维列、时间与任务索引；三视频逐帧解码并校验帧数、PTS、尺寸与FPS；使用真实Isaac-GR00T读取器检查每条起/中/末窗口，记录1×34状态和40×66动作。
7. 生成 `reader-validation.json`、`pipeline-provenance.json`、审核快照与 `dataset-acceptance.json`。收据绑定产物文件哈希；已验收包不得加日志、增删文件或改内容，后续validate只核验旧收据，不给已变内容重新背书。

50Hz是动作网格和输出视频索引，**不是三相机50Hz曝光**。相同JPEG可在多个动作时刻复用。禁止单独删重复图像、只剪MP4或只删Parquet行；如裁剪/重采样，所有模态同步处理并重新验收。PICO/相机源时戳与工作站接收时间不可混称精确传感器同步；Legacy Body时间戳不能单独证明传感器新鲜度或motion_ready。

输出结构：

```text
<run>/
  run-request.json
  conversion.log
  converted/...
  cleaned/
    data/chunk-000/episode_*.parquet
    videos/chunk-000/observation.images.{ego_view,left_wrist,right_wrist}/episode_*.mp4
    meta/...
    human-review.json          # 正式人工审核路径有此文件
    pipeline-provenance.json
    reader-validation.json
    dataset-acceptance.json
  run-result.json             # 全流程成功后才产生
```

formal_training_eligible仅表示数据包通过对应门禁，不证明训练、离线预测、仿真或真实抓取已经成功。离线处理隐藏CUDA，不加载VLA模型；不要为检查数据占用现有GPU推理流程。

## 10. 验收后交付与训练边界

本节只说明已有能力，本文不会执行上传/训练。正式上传例：

```bash
./pipeline.sh upload \
  --dataset /opt/g1/workspace/datasets/colleague_task_v001_train/cleaned \
  --receipt-output /opt/g1/workspace/reports/colleague_task_v001_train_handoff.json
```

验证集独立上传。固定路线为本机→`jump-user@192.0.2.10:22`→在跳板机执行SSH到`unitree@192.0.2.20:22`。目标根 `/srv/g1/sonic-vla`，正式包进 `datasets/accepted/<dataset_id>`；工程包需显式 `--engineering` 且仅进 `datasets/engineering/`。ProxyJump不能替代跳板身份；同事认证需其本人已有授权，不复制任何密码/私钥/原机认证socket。

数据在唯一.partial暂存目录接收，远端重算全量哈希后原子发布；相同内容允许already_present，不同内容拒绝覆盖。当前失败partial不自动续传/清理；超时后保留证据，必须拿该dataset_id的远端哈希收据，不能看到目录存在就判成功。旧raw同步入口已禁用。

正式训练仍需独立人工审核train/validation、完整锁定基座与环境、8×L40S每卡至少35GiB空闲；不得停止别人作业或改参数凑通过。默认冻结LLM/视觉主干，只训练投影层与动作头。工程/skip-weight-loading checkpoint、一步梯度、loss下降、常量夹爪零误差都不能冒充正式模型或任务成功。

## 11. 常见失败与处理

| 现象 | 首先核查 | 处理边界 |
|---|---|---|
| PC Service存在但没有PICO包 | 客户端前台、Full Body/Send、网络、APK/SDK/服务组合 | 不删新鲜度检查，不拿旧缓存当新输入 |
| policy/hash报错 | 文件是否漂移、是否搬家、上游commit是否一致 | 保留差异；不改锁凑通过，先走明确迁移修订 |
| LowCmd不静默/已有控制器 | 是否别的会话或电脑拥有控制权 | 不杀其他作业，不再启动第二控制器 |
| 数采未ready | 身体/相机/模式/Dex1状态和命令是否齐全、年龄、DDS网卡 | 不自动启控获取状态；不要仅凭图像能看就开始 |
| 左右错 | physical_to_wire与相机角色、接线是否变 | 确认物理左右；不凭topic名字交换两次 |
| 夹爪退出但身体还运行 | dex1-mapping.log、gripper-degraded.json | 由现场操作者处置；不可假定整机已停或自动重启夹爪 |
| no token/short/stale | context/events、token_state64、完整长度 | 保存失败，不填零、不用29D替代 |
| raw有重复相机图 | 相机实际频率与采样网格、冻结证据 | 不能只去重图像导致跨模态错位 |
| 输出已存在 | 是否旧结果、失败部分目录 | 换新版本目录，保留失败证据 |
| 语音不可听 | voice环境/模型、env-tv、RPC、现场扬声器 | RPC≠可听；不把失败播报当保存成功 |
| 验收后哈希变化 | 文件新增/修改/软链接、日志是否写进cleaned | 拒绝交付；保留原收据，不能原地重签掩盖变化 |
| 无成功审核/验证session | 人工实际任务审核与集合来源 | 正式数据BLOCKED；仍可进行明确engineering_only验证 |

## 12. 直接复制给同事 Codex 的任务提示

```text
请先阅读《SONIC_Dex1_手柄遥操作数采与清洗_同事Codex复现说明.md》和随包AGENTS.md。
目标：在我的电脑复现相同的PICO→SONIC身体、Trigger→Dex1、原始录制→人工审核→token转换→官方清洗→真实读取器验收链路，并与原工作站用证据同步进度。

先做本地只读盘点：OS、路径、Git提交/修改/新增文件、Python环境、锁、文件哈希、上游补丁、SDK/PC Service版本、模型与vendor许可证。确认已收到自定义源码，不能只clone官方仓库就声称复现完成。
列出与文档快照的差异及最小实施步骤，然后执行已获授权的普通可逆离线工作。不要启动真实控制、DDS发布器、相机/串口服务，不自动切运控、不改变网卡、不杀现有作业、不上传、不下载模型、不启动训练。
优先用获准共享的完整episode做engineering_only转换→官方清洗→真实GR00T读取器与哈希验收；没有样本就明确列为缺失，继续做可独立完成的源码/环境检查，不伪造数据。测试和输出写新reports目录。
当前contract锁定原机绝对路径，若与本机不同，先形成迁移差异与可审查补丁；受保护规范/锁的修改需要用户明确修订授权，禁止自行改锁绕过。保留原件、哈希与回滚。
人工回放成功判定由实际审核人给出；你不能自动批准。工程数据不能进入正式训练。未来真机步骤需要对具体操作的现场授权、支撑、旁站、独立急停，并确保只有一台电脑拥有控制权。
每阶段保存：命令、退出码、日志、源/产物哈希、实际输出维度、PASS/FAIL/BLOCKED/未执行、验收局限与下一步。完成离线链路后报告，不因安装成功就宣称机器人或抓取任务成功。
```

### 双方同步进度用同一张表

每次交接填写实际值。报告放reports，不能塞进已验收cleaned目录；不包含凭据或未经授权的原始影像。

| 字段 | 要填写什么 |
|---|---|
| 日期/操作者/电脑 | Asia/Shanghai时间、机器标识 |
| 文档与代码版本 | 本文件SHA256、WBC/GROOT commit、本地补丁/自定义源码清单哈希 |
| 策略与设备 | contract/policy-lock哈希、路径迁移授权记录、网卡、物理左右和相机映射 |
| 输入来源 | 完整session/episode标识与指纹；合成/工程/正式类别 |
| 人工审核 | reviewer、note、decision、trim、session级split |
| 录制 | complete、有效条数、失败理由、实际路径 |
| 转换/清洗/读取 | 命令、退出码、源/输出帧数、state/action shape、reader报告 |
| 验收/交付 | dataset_id、收据哈希；远端对应ID的哈希结果，未执行写未执行 |
| 现场动作/训练 | 是否执行及授权、具体动作与观察；没有执行不得写PASS |
| 阻塞/下一步 | 缺失项、失败证据位置、谁负责处理 |

## 13. 来源和本次核对范围

优先级：受保护AGENTS/contract → 当前源码与指纹 → 对应运行收据 → 旧说明。旧README存在早期D435i假设、旧端口和旧功能未接通描述，本文已用当前源码及camera-roles纠正，未改旧文件。

关键本机来源（随源码/报告交接；未随本文复制）：

- G1：`AGENTS.md`、`capture/{record,core,sonic_camera,speech,pcm,neural_voice,robot_audio}.py`、`capture/voice/manifest.json`。
- G1：`sonic_pipeline/{cli,settings,policy_guard,manifest,review_page,convert,local_workflow,validate_dataset,acceptance,upload_dataset,runner}.py`及contract/policy-lock。
- WBC：`official_sonic/{run_real_teleop,streamer,dex1_mapping,dex1_bridge,unitree_dex1,dex1_transport}.py`、console源码、profiles。
- 工程回读：`reports/local_workflow_20261027/ENGINEERING_VERIFIED_SOURCE/cleaned/reader-validation.json`及dataset-acceptance.json。
- 历史工程交付：`reports/local_workflow_20261027/ssh-engineering-handoff.json`；对应ID为 `09fbfe6625e69dac5d0b824743052aa5d77710a77a7b5180b48962c49c9426df`。另一包 `c0ec03f19a33a2ffe8d1a1919481d76f6dbf32b49071c789e9d302c008e2da4d` 的upload-final.log记录300秒超时，本次未远端复核。
- 现场阶段证据：WBC `official_sonic/全身遥操作验收-20261027.zh-CN.md`、`PICO按键速查.zh-CN.md`、profiles与相关real_sessions；旧验收中的“头D435i/数据schema未完成”是历史阶段状态，不覆盖后续工程数据证据。

官方工具参考（当前实现以锁定源码为准，本文没有实时刷新网站）：

- [SONIC数采与Exporter](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)
- [SONIC全身遥操](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vr_wholebody_teleop.html)
- [SONIC VLA流程](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vla_workflow.html)

本次文档核对包括policy与固定官方数据源码检查、关键环境包元数据、CLI参数和历史工程报告；没有重新进行现场动作、完整数采、模型训练或远端交付验收。同事电脑的可用性要以其本机实际验收为准。

## 附录：交接时核对的关键文件SHA256

以下是编写时的源码快照，用来发现版本差异；不是允许自动替换文件的指令，也不是完整软件包的全量清单。相对路径以每个分组根目录为准。

### G1 /opt/g1/workspace

```text
f6cc5e29af9afb7053a01faf4ce8266cbb00ba3e5d21273752a44278daa9ea84  AGENTS.md
4f8643a5ed6ef151af8c9f00cf75c8b55d3718bd95354d824f4d185b97c40b9d  pipeline.sh
72c087eef89972c7ddd35ddc3cad088746597ff0b0e9fceb78f339e7a5a664a5  capture/start.sh
1de8c600795768cfebbe28bc6a253adfd399ab8c17a96f8f6327a3f9ba50991a  capture/record.py
733ccd863dd9ffd7d98f873470262c2efcf6a67ada05c3db6961bde56eea8328  capture/core.py
5a5e8804a766eb18ef3e6a0ef2c65b8fc27914abb371c47fd5464e79902d4f74  capture/sonic_camera.py
34befd9d4572e84cb119b096b503684c4e88256d5e4ca1c825065317638c9f7e  capture/pcm.py
bc92192c4f0d12968c38261631a523939288e3455d1695c25b341984febd7b10  capture/neural_voice.py
a9ba2002bd461901821060d7a7022b0418d37317a9f8d475e1721d60c52324b0  capture/robot_audio.py
968a4329cb15e58f76757a445e448be80f2f4b30976faeb9fc2aae6ca2eb8442  capture/voice/manifest.json
c5a89cfc23dc518d6d137aa82b611c45eb3821d6d88327c17fbcade5dd0fb32c  sonic_pipeline/workflow-contract.json
7ef95b1f7dd5c2276babf6c2842f65b9526465785e099a1bed0d0d64211a9a8a  sonic_pipeline/policy-lock.json
be7dc27d07c840a38cf50da0a8e63e97d1034e512dbd28e4ed9b14fcee1d7d20  sonic_pipeline/convert.py
e627cb0ae3dc3f765cd407a76fb180871ebae90aaea1489ace63550a50a905e6  sonic_pipeline/local_workflow.py
facccb29491b3785f16a621d393b58d933663815c1cd2479cc3b10a8d830d35f  sonic_pipeline/validate_dataset.py
dcceae70617b024de10e0a3f82c029b5fd0d36848d86bf9c95ac882a56e1fe15  sonic_pipeline/acceptance.py
```

### WBC /opt/g1/GR00T-WholeBodyControl

```text
b00771cf2f7930f0beab6750080b25f44639c7dd8ebdf881d8afaade2bd39b22  official_sonic/run_real_teleop.py
1ac3a21c4bb80835304ace1dc3055d4010131497bd89ea966679de05439d27c7  official_sonic/streamer.py
b966f667748da3466950e4f9bf16868baf2aa2f2593a870e7fd6ac39ac7b87f1  official_sonic/dex1_mapping.py
06b8b62b2f3f32ad675ccd95c2d6efc49e8ddfaa219c4acfa3f4547011515067  official_sonic/dex1_bridge.py
dec52a3d6dbb9b0db6cfceb3c0e4fbd4f839136f5925ea894dc3bdfc303ff39a  official_sonic/unitree_dex1.py
bbdac7599983dd54c55ef1981008329adb320b927de094e36fda0484438c90d1  official_sonic/dex1_transport.py
31b8683e86313003af8080826e38173a71a431d41aee4f65267b535ea2357a32  official_sonic/console/app.py
a631c712fb5f27ef2e69ed20284ef9464c35d429be1519c5bf5be92f5c73cff1  official_sonic/console/backend.py
8ec3aeb6ca1cfa9ebe5eab8dcf329a7f93109b7c6509ea060ac538a2313bed31  official_sonic/profiles/dex1-hardware.json
ef6272a980215b5d49e45455835965a98de17706cc71a963e88bc31dddec073b  official_sonic/profiles/dex1-upstream-lock.json
7a12bfb5b1e466ba660d9c882326be1cc02193e6fae9a5ee9956455da1b2d822  official_sonic/profiles/camera-roles.json
338c2956426ec2238214bed57564ec2abc6fe8e4f3673fb16c85c75a1c282021  gear_sonic/scripts/pico_manager_thread_server.py
cb2ba793c74982d0c542fc5733177afd179131ac5f16c9693361d9ec21eede81  gear_sonic/utils/teleop/input_readers.py
0d86a739511ea016e25f1d8b54840efd2b8bbf9d121f749450c8437e3bf3b405  gear_sonic/camera/composed_camera.py
9b7fb20af155f47924a75edcce858e54d21824670883990477aba1f9bf0950a8  gear_sonic/camera/drivers/usb_camera.py
5ebabae815e2ce45a10674fd60bdcd97f9e948cb1c50517e5d851008a9be204c  gear_sonic/data/exporter.py
af9971ab4fd96e3821a3423974a406fdb8432e1b0b75f720c819ff4e3e5127cc  gear_sonic/scripts/process_dataset.py
```

