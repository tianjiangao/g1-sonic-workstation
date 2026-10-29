> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# SONIC 全身遥操数采

> 2026-10-27已授权修订：本机数采、人工审核、token转换、官方清洗与验收后，才通过SSH交付远端训练。完整入口见`/opt/g1/workspace/sonic_pipeline/README.zh-CN.md`。下文capture/export.sh与工作台旧导出是29D诊断格式，不能作为66D正式训练数据。

部署位置 `/opt/g1/workspace/capture`。复用现有 SONIC/PICO/Dex1 控制程序；本录制器只有 ZMQ SUB 和 DDS ChannelSubscriber，不启动控制服务、不创建发布器、不发送运动指令。与用户贴的宇树 `g1_ctrl` 教程不是同一控制链。

## 现场运行

先按已验证流程由现场操作者启动现有 SONIC、PICO 和 Dex1。机器人支撑、清场和急停必须保持可用。当前机器人控制服务处于 inactive，录制器不会为获取状态而启动它。

另开工作站终端执行：

```bash
/opt/g1/workspace/capture/start.sh --task '拿起物体并放到目标位置'
```

默认连接 Orin `192.168.123.164`：身体状态/配置 5557、相机 55555/55556/55557；PICO 在工作站 `192.168.123.99:5556`，扳机诊断消息 5558；Dex1 在 `enp4s0` 仅订阅 DDS。左右映射读取已有 `official_sonic/profiles/dex1-hardware.json` 的已验证物理映射，不修改它。数据保存在 `/opt/g1/workspace/recordings/SESSION_<时间>/`。

看到 `"ready": true` 后，在录制器终端输入 `s` 回车开始，再输入 `s` 回车保存；可重复。也接收现有 SONIC `manager_state` 的录制开关事件（官方 Left Grip+A）和丢弃事件（Left Grip+B）。不要混用宇树旧教程的 A/SELECT 或 s 操作语义来控制 SONIC 身体。

输入 `q` 回车或 Ctrl+C 只退出录制器，**不会停止机器人**。请先正常结束并保存 episode，再退出。身体停机仍走现有已经验证的 SONIC 现场停机流程，遥控器急停须随时可用。

只读就绪检查：

```bash
/opt/g1/workspace/capture/start.sh --task '只读验收' --probe --seconds 15
```

退出码 0 表示本次结束时数据输入满足就绪约束；2 表示缺失/过期。probe 永不创建 episode。`--no-dds` 只用于相机/ZMQ 排查，不能完成 Dex1 就绪检查。

## 保存内容与数据质量

每段包含 `frames.jsonl`、`events.jsonl`、`context.json`、`episode.json` 和内容哈希命名的 JPEG。保留完整头部 480×1280 双目图以及左右腕 480×640 图，不裁眼、不翻转、不交换相机。JPEG 相同内容复用文件，但每次收到的相机消息都有接收事件，不能把重复消息数当独立拍摄帧数。

身体数据直接使用 SONIC `g1_debug.body_q` / `last_action`（29 维、MuJoCo 顺序、上游已加默认偏移/缩放）；Dex1 使用物理左/右各一个 q（rad）。action 是观察到的实际 WBC/Dex1 命令，不是成功抓取标签。完整原始 g1_debug、PICO pose/planner/manager/command/trigger 和 Dex1 q/dq/力矩/命令字段在事件日志保存；非相机 ZMQ 同时保留原始报文 base64。事件只在录制中保存，开始时另保存最新上下文。

15 Hz 是录制抽样频率；不是承诺三相机曝光同步。身体/PICO模式/Dex1命令与反馈接收年龄上限 0.25s，相机 0.5s，机器人配置 30s。缺失、过期、非有限数、错误维度、图像解码失败、明显调度间隔、DDS回调队列溢出、磁盘低于5GiB时阻止开始或将当前段标记不完整。恢复后不会自动续录，需操作者重新开始。退出时未主动保存的段标记不完整，原始文件保留。

ZMQ PUB/SUB 没有端到端序号/交付确认，无法证明零丢帧；当前 JPEG 协议无曝光时间戳/帧号，不能检测所有相机冻结。机载时钟明显偏差，本版仅记录工作站 epoch_ns 与 monotonic_ns 接收时刻，不修改机载时钟，不把接收时刻伪称传感器时刻。需要严格同步时还必须增加采集端时戳/帧序号与时钟方案并独立验收。

## 导出与回读

先保存得到 `complete=true` 且至少2帧的段，再在机器人控制之外执行离线转换：

```bash
/opt/g1/workspace/capture/export.sh \
  --episode '/opt/g1/workspace/recordings/SESSION_实际时间/episode_000000' \
  --output '/opt/g1/workspace/recordings/新数据集名称'
```

复用现有 `.venv_data_collection` 内官方 `Gr00tDataExporter` 和固定 LeRobot 版本，不重新安装、不访问远程仓库、不上传。导出前校验每张 JPEG 哈希/尺寸、向量和时间间隔；输出存在则拒绝覆盖。写出后回读 Parquet、解码全部视频并检查帧数/帧率；结果保存在 `capture-validation.json`。

明确使用自定义 `g1_29_dex1` schema：`observation.body(29)`、`action.body(29)`、`observation.dex1(2)`、`action.dex1(2)`、三路视频和 modality.json。不伪造 Dex3 七关节，不宣称可直接接入预训练 N1.7；后续需要匹配训练 embodiment、关节名称、任务与质量审核。原始实际时间保留在源段，LeRobot视频/表格使用15Hz索引时间；`training_ready=false` 保留。

## 软件验证与回滚

```bash
cd /opt/g1/workspace
/opt/g1/GR00T-WholeBodyControl/.venv_sim/bin/python -m unittest discover -s capture/tests -v
```

合成端到端验证输出必须位于报告目录，以 `SYNTHETIC_ONLY` 标识：

```bash
/opt/g1/GR00T-WholeBodyControl/.venv_data_collection/bin/python \
  -m capture.tests.integration_offline \
  '/opt/g1/workspace/reports/新的_SYNTHETIC_ONLY_目录'
```

现有报告 `/opt/g1/workspace/reports/wbc_capture_20261027`。停止本录制器后归档 capture 目录即可撤回适配代码。保留 recordings 和报告里的数据；不停止其他控制/相机进程，不改 systemd、不改模型、不覆盖旧工程，不自动清理数据。

来源：[NVIDIA 数采](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)、本机已有固定上游及 SONIC Dex1 映射。运行环境与精确源码哈希见报告 `manifest.json`。

## 中文播报与条目确认（2026-10-27更新）

桌面“启动遥操与数采”只启动系统，不自动开始录制。等待“数据就绪”，点击“开始采集”：实际创建片段后播报“开始采集，第N条”。点击“结束并保存”：文件落盘确认完整后播报“采集结束，第N条已保存，共F帧”。缺数据时播报“未开始采集”，断流或故障播报“采集中断，未保存为有效片段”，不播报成功。

当前条数、本次已保存条数、最近保存路径也显示在工作台。编号由任务目录take-counter.json持续分配，中断条目也占编号，避免重启后重复。语音使用工作站已有Speech Dispatcher/espeak-ng中文语音，异步播放，不引入云服务或GPU推理；声音是否可听需在实际输出设备确认。原始段与LeRobot导出均保持原有数据结构。

语音输出更新：按用户要求改为 **G1自身扬声器**。文字合成TtsMaker在当前机器人上返回成功但未听到，不能当成可用。正式路径使用系统已有libespeak-ng离线生成16kHz/单声道/16bit中文PCM，通过现有独立env-tv中的官方AudioClient.PlayStream发送到机器人。遥操与夹爪环境不升级、不替换。客户端先等待voice服务查询成功，每包检查返回码，语音失败在录制状态speech字段报告，录制不因语音失败阻塞。程序回包成功仍不能代替现场听音确认。
