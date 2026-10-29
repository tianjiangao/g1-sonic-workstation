> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# PICO × SONIC × MuJoCo 仿真入口

状态：2026-10-26 真人仿真 POSE 验收通过。用户确认左右手对应正确，坐下动作也由用户主动发起。约83秒动作跟随已记录；真机遥操作和数据集导出不在本轮已验证范围。

## 启动与停止

在项目根目录运行：

```bash
./check_sim_safety.sh
./start_sim_teleop.sh
```

启动保持前台；另一个终端可运行：

```bash
./status_sim_teleop.sh
./stop_sim_teleop.sh
```

仅诊断 PICO：`./start_sim_teleop.sh --mode probe`。
离线策略测试：`./start_sim_teleop.sh --mode offline --headless --seconds 30`。

所有日志位于 `sim_teleop/logs/<时间-编号>/`，当前实例信息在 `sim_teleop/state.json`。status 中历史数据不表示当前仍运行。

## 实际结构

PICO XRoboToolkit → 宿主已有 PC Service → 固定 127.0.0.1:60061 中继 → 私有 Unix socket → 仅 lo 的临时 user/network namespace → SDK 独立采集进程 → 官方 PICO Manager 的坐标转换/SMPL/FK → ZMQ 5556 → SONIC 仿真专用程序 → Unitree DDS domain 0 → MuJoCo。

采集进程与 IK/FK 进程隔离，避免本机 native 计算持有 Python GIL 时阻塞 SDK callback。仿真运行不需 sudo，不修改物理网卡、宿主路由或防火墙。每次运行重新建立 namespace；不允许 fallback 到宿主网络。check 会检查运行中的子进程 namespace、接口和路由，并再次执行独立隔离探测。

仿真 C++ 使用 `SONIC_SIM_ONLY` 构建，启动前检查 namespace；禁用机器人 Audio/MotionSwitcher RPC，原有真机二进制未覆盖。Unitree 库搜索路径仅对该进程设置。ROS RMW 环境为 FastDDS、domain 117，当前仿真专用构建禁用 ROS2 输出；电机通道仍是 Unitree DDS domain 0。

## 操作

头显端先关闭 **Tracking → Data & Control → Switch w/ A Button**，手动保持 **Send=ON**。官方客户端的此选项会令 A 键切换 Send，与 SONIC 的 A+B+X+Y 启动、A+X 切换模式冲突；按键后可能整帧断流，引发安全退出。来源：https://github.com/XR-Robotics/XRoboToolkit-Unity-Client 。此设置是否已关闭需由佩戴者确认，工作站无法直接读取其 UI 状态。

等待 `sonic.log` 中 `Init Done`，并确认窗口正常、PICO 数据新鲜。中立站姿下按一次 A+B+X+Y 标定和启动，松开等3秒，然后按 A+X 进入 POSE。先只抬左手，再只抬右手。停止入口优先使用 stop 脚本。

MuJoCo 初始有虚拟支撑；观察到第一条推理 debug 消息后自动释放。无头模式可测试通信和动力学，但不能替代真人视觉验收。

## 新鲜度的已知限制

本机实际 Body JSON 只有 joints，没有整体 body 时间戳；23 个关节 IMU t 为 0。保留这些原始值，不伪造关节时间戳。门禁要求完整原子24关节包、源 envelope 时间推进、每个关节内容近期实际变化，并验证所有非零 IMU 时间戳推进；NaN/Inf、错误 quaternion、缺关节、倒退/重复时间戳会拒绝。帧/关节超过250 ms未更新会锁存故障并退出整套仿真，不自动重新接管。

零 IMU 时间戳关节的真实传感器采样年龄仍无法直接证明；完全静止或量化不变的姿态可能保守触发退出。不能将 envelope 或头部时间戳单独作为全身有效依据。

## 数值保护与证据

C++ 仿真输出在发布前拒绝非有限值，对关节位置按模型范围限幅并记录饱和计数。限幅不证明策略质量或稳定性；持续饱和需单独定位。dds.json记录实际发布频率、计数、间隔和限位故障；telemetry记录收到的pose/command/debug；sim-state.jsonl记录物理仿真状态。软件接收延迟不等同于头显动作到机器人响应的端到端延迟。

## 环境

复用 .venv_sim、.venv_teleop、现有PC Service及模型，不安装新依赖。默认使用匹配的sonic_v1_1 encoder/decoder/observation配置及现有Planner。GPU须有足够空闲显存，启动器不自动停止任何其他服务。Strata曾按用户指令手动停止，未设置自动恢复。

## 验证

```bash
.venv_teleop/bin/python -m unittest discover -s sim_teleop/tests -v
./check_sim_safety.sh
```

真实G1未测试、未连接、未修改。禁止把此入口用于真机。
