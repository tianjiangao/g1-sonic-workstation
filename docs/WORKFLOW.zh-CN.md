# 从遥操到数据与回放

本文给出入口及顺序；执行前完成 SETUP 的版本、现场配置和策略审核。所有示例路径以自己的新 workspace/WBC 为准。终端退出录制器不会停止身体控制，录制按钮和急停职责不同。

## 遥操与录制

先阅读 `docs/reference/PICO按键速查.zh-CN.md` 及 `DEX1映射说明.zh-CN.md`，由现场操作者按官方流程完成支撑、急停、PICO 校准、身体状态与夹爪映射检查。WBC 中 `start_real_teleop.sh` 和 `official_sonic/run_real_teleop.py` 是物理控制入口，必须单独审核；不要在阅读 README 时自动运行。

工作站入口为 WBC 中 `official_sonic/console/app.py`。它有遥操、设备、日志、片段与 3D 回放等页面。代码包含启动时夹爪张开的选项和现场确认，不能在夹爪行程被占用时启用；详见参考文档。UI 中的一些 blocker 文案保留历史实现，当前验收范围以 VALIDATION 为准。

录制器是被动 subscriber，不为获取状态而启动控制。完成版本与现场配置后，在 workspace 运行：

```bash
# 先做只读输入探测，不创建 episode
"$WBC/.venv_sim/bin/python" -m capture.record --task '只读检查' --probe --seconds 15 --robot-host YOUR_ROBOT_IP --pico-host YOUR_WORKSTATION_IP
# 实际录制通过工作站或同一入口去掉 --probe；由操作者开始和保存
```

`WBC` 在命令中指你的官方 checkout 绝对路径。先确认参数帮助和 DDS 网卡。缺失、过期、非有限数据、错误维度、队列溢出或磁盘不足会阻止开始或标记不完整。语音只在实际状态改变后反馈，保存成功与任务成功是两件事。

每段保留 frames/events/context/episode 与图像内容哈希。录制抽样约15Hz，正式 token 转换使用50Hz动作网格；接收时间不等于曝光时刻。

## 人工审核

以下命令需先建立经审核的站点策略，`pipeline.sh` 中的 Python 可用 `G1_PIPELINE_PYTHON` 指定为 data 环境。

```bash
bash pipeline.sh inventory --raw /ABS/RAW --output /ABS/WORKSPACE/datasets/reviews/inventory.json
bash pipeline.sh review-page --manifest /ABS/WORKSPACE/datasets/reviews/inventory.json --output /ABS/WORKSPACE/reports/review
```

本机打开生成的 index.html，检查任务、完整性、图像、实际反馈和命令。用 `review` 命令写新 manifest，decision 为 approved/failed/device_test/pending，并填真实 reviewer、note 和 split；批准仅限人工实际确认任务成功。按完整 session 划分 train/validation/test，不把相邻切片放到不同集合。不完整片段不能批准。

## 转换、清洗和验收

```bash
bash pipeline.sh local-run --manifest /ABS/reviewed.json --split train --output /ABS/WORKSPACE/datasets/task_train_v1
bash pipeline.sh local-run --manifest /ABS/reviewed.json --split validation --output /ABS/WORKSPACE/datasets/task_validation_v1
```

转换只用采样时刻及以前、仍新鲜的必要事件。身体状态和真实64D token是不同字段；保留左右各1D Dex1，不补造七维手指。官方 exporter 写新目录，官方 `process_dataset.py` 清洗同样写新目录；当前 VR3PT/Dex1 禁用零SMPL清洗，所有模态同步裁剪/重采样。

验收包括 Parquet/三路视频数量与时间、维度/单位/任务、真实 Isaac-GR00T reader 的起中末窗口以及全部文件哈希。34D 状态，40×66D 动作。收据绑定审核、provenance 和 reader 报告；已验收目录不要增加日志或修改内容。

工程检查使用 `local-run --engineering-episode /ABS/episode --output /ABS/WORKSPACE/reports/NEW_ENGINEERING_ONLY`。它不能自动批准数据，也不能进入正式训练。

## SSH 交付与训练

`upload --dataset /ABS/cleaned --receipt-output /ABS/WORKSPACE/reports/handoff.json` 只交付已验收数据。按站点契约先登录跳板机，再由跳板机自己的 SSH 身份登录目标；ProxyJump 不等于该身份。逐文件远端重算哈希后原子发布；内容不同拒绝覆盖，失败 partial 保留。工程包必须显式 `--engineering`，只能进入 engineering 命名空间。

上传不启动训练。训练前仍需独立人工验证集、锁定基座与环境、8×L40S 且每卡至少35GiB空闲；不足即停，不结束其他作业。`train-plan`、`evaluate-plan` 和 `sonic_pipeline/cloud/` 提供计划/执行接口；远端引导和下载脚本必须逐项检查后才执行。工程 smoke checkpoint 不可部署。损失下降和离线误差不证明任务成功。

## real2sim：真实反馈的被动回放

完成模型构建后，从 WBC 运行：

```bash
.venv_sim/bin/python -m offline_replay.demo --episode /ABS/COMPLETE_EPISODE
```

localhost 页面提供时间轴、播放速度、实际反馈/目标角切换、全身与夹爪近景及保存图像。29D body_q 已是 MuJoCo 顺序，不能再次重排或加默认角；64D token和人体SMPL不是关节角。夹爪真实数据仍是2D，模型4个滑动关节仅作显示；电机角到毫米尚未实物标定。无可靠全局基座位姿，固定 freebase。

它不运行策略、DDS/ZMQ控制或 physics stepping，不证明接触抓取或全身动力学。独立 `sim_teleop` 是另一条隔离仿真路径，不把回放结果称为该路径的策略成功。
