> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# SONIC 官方流程配置与当前验收状态

**2026-10-28 SSH 更新：** 工作站现在自动连接 G1、复用会话并在需要时重新建立连接，不再依赖先手动登录终端。使用专用密钥，不保存密码；不会自动启动遥操或 INIT。验收、故障提示及回滚见 [G1 自动 SSH](console/SSH.zh-CN.md)。

**最新更新（Dex1映射）：** PICO 左右扳机已分别接入宇树官方 Dex1 控制循环；隔离DDS与软件测试通过，真实开合待操作者下一轮验证。桌面控制台新增“开始下一轮真机验证（SONIC + Dex1）”，需现场确认后启动原版SONIC；完整训练数据采集仍未验收。详见 [Dex1映射说明](DEX1映射说明.zh-CN.md)。下文早期“真机按钮锁定、Dex1控制未接通”已由此更新替代；数据模型与头部相机未完成项仍有效。

本目录按用户最新要求整理：使用官方遥操作、相机、采集器及 LeRobot 导出，不使用本轮自定义 POSE 启动门或改写的控制状态机。真实运动留给用户现场验证。**目前不是完整真机就绪状态。**

## 最新进展：主机统一入口与重新连接（2026-10-26）

桌面及应用菜单已添加 **SONIC 工作站**。这是本机配置与作业入口，调用官方采集器和已验收的隔离仿真，没有新的运动控制算法。可保存任务/数据目录、启动或复用 PICO PC Service、检查 PICO 数据、做采集写盘自检和隔离仿真，并查看日志。真机和真实采集入口仍锁定，不把一个窗口做出来当成真机验收通过。

详细用法见 [控制台说明](console/README.zh-CN.md)。本轮官方导出器已写出并回读一个合成自检 episode：12 帧、50 Hz、头部/双腕共3路视频全部可解码；不是实际机器人数据。

有线链路现已恢复，SSH 可登录。Orin 官方相机环境已通过离线安装、依赖检查和模块帮助检查；34 个 wheel 哈希与工作站一致。运行时须先进入 `/home/unitree/sonic_official_camera_7f151314`，避免旧仓库的同名 package 遮蔽新相机模块。RealSense SDK 当前枚举结果仍为 `[]`。

接口变化：工作站新增 ASIX USB 千兆网卡 `enx9c69d388b5b0`；Orin 的 Genesys Hub `05e3:0610` 消失，内核记录 USB `1-2.2` 断开；两台机器均未看到 D405。证据在 `evidence/reconnect/`。原真机服务仍 failed/stopped、enabled，未发现 SONIC 控制进程，本轮未启动真机。

下文先前的“网线断开 / 相机依赖未安装”是上一轮历史状态，以上更新为准。Dex1、真实相机识别/映射和原生 PICO 接口的未验收项仍有效。

## 已完成

- 工作站 `.venv_data_collection` 已安装官方 `gear_sonic[data_collection]`，LeRobot 固定为上游指定提交 `a445d9c9da6bea99a8972daa4fe1fdd053d711d2`。
- 使用 CPU PyTorch 2.6.0 / torchvision 0.21.0；采集器不需要额外 GPU 推理。未修改 `.venv_teleop` 或 `.venv_sim`。
- 143 个包的依赖检查通过；官方采集器、一键启动器帮助入口通过；官方机器人 FK、27 个数据字段及双腕图像字段加载通过。
- 已生成官方 CLI 参数配置，采集与一键启动配置通过官方 Tyro 类型解析；未调用它们的启动函数。
- 相机源码取自本机上游提交 `7f151314d4d1606544bf249d2a7a1cb754c64582`，逐字归档，没有编写相机驱动。已传至 Orin 的 `/home/unitree/sonic_official_camera_7f151314`。
- 已准备 ARM64/Python3.10 相机离线依赖，共 34 个 wheel，约 340 MiB，包含 RealSense SDK。SHA256 见 `evidence/camera-wheels.sha256.json`。
- 仿真回归 16 项通过；仿真网络隔离和启动入口保持原样。

## 当前阻塞，不能省略

1. **工作站有线连接断开。** 最新 `enp4s0` 为 `NO-CARRIER`、DOWN，没有原来的两个 IPv4 地址；SSH 超时。没有修改网卡、路由、DNS 或防火墙。离线 wheel 尚未传完，不能宣称 Orin 相机环境安装成功。
2. **Orin 未枚举到 RealSense。** 最近登录时 `lsusb` 没有 Intel/RealSense，且没有 `/dev/video*`。用户确认 D405 接 Orin，但实际设备识别尚未通过，不能编造序列号或头/腕映射。
3. **Dex1 与 SONIC 当前部署接口不匹配。** 当前官方部署实现固定为 Dex3 七关节和 `rt/dex3/...`。名称含 gripper 的 Python IK 也生成七关节向量，不是 Dex1 驱动；官方采集器默认 G1+ThreeFinger 模型。没有找到可通过参数切换到 Dex1 的现成 SONIC 部署入口。不能将 Dex3 的零状态当成 Dex1 采集结果。
4. **多 RealSense 的官方实现缺口。** 本地及在线主分支的 composed camera 在 RealSense 分支没有传递 `device_id`，而驱动默认打开排序后的第 0 个设备。因此暂不提供看似可用的三相机序列号配置，避免三个角色争用同一相机或误标头/腕画面。
5. **PICO 原生入口尚待兼容性确认。** 仿真成功使用的是已验证的原子数据包读取适配；SDK 的 body timestamp=0 与本地严格 Reader 不兼容。没有把这项已知问题隐藏成“原生官方入口已通过”，也没有跳过新鲜度检查。

## 官方组件与配置

当前优先保留官方支持的分机连接：工作站 PICO → ZMQ 5556 → Orin 原版 SONIC → Unitree DDS；Orin 状态 ZMQ 5557 和相机 ZMQ 5555 → 工作站官方采集器。

| 配置 | 用途 | 边界 |
|---|---|---|
| `profiles/orin-controller.args` | Orin 原版 `target/release/g1_deploy_onnx_ref` 的参数 | 身体控制配置；不是 Dex1 已适配证明；会控制真实机器人 |
| `profiles/pico.args` | 官方 `pico_manager_thread_server.py` 参数 | 原生 Reader 兼容性未验收 |
| `profiles/exporter.args` | 官方 `run_data_exporter.py` 参数 | 状态接 Orin、姿态接工作站；双腕字段启用，但硬件和 Dex1 schema 未就绪 |
| `profiles/workstation-all-in-one.args` | 官方 `launch_data_collection.py` 配置 | 改为工作站运行 C++ 的另一种官方布局；与 Orin 控制器互斥，未执行真机启动 |

两种控制布局不可同时启动。当前真实摄像机、Dex1 和 PICO 原生入口的阻塞解决前，不把这些参数文件作为完整验收通过的一键启动器。

可安全重复执行的软件检查：

```bash
cd /opt/g1/GR00T-WholeBodyControl
uv pip check --python .venv_data_collection/bin/python
.venv_data_collection/bin/python gear_sonic/scripts/run_data_exporter.py --help
.venv_data_collection/bin/python gear_sonic/scripts/launch_data_collection.py --help
```

官方录制操作是左 Grip+A 切换录制，左 Grip+B 标记丢弃；必须先验收实际相机、关节和夹爪状态。PICO 的 Switch w/ A Button 保持 OFF、Send 保持 ON。官方模式顺序保持 ABXY 校准/启控 → AX 进入 POSE，不再使用本轮自定义 POSE-only 流程。

## Orin 相机离线安装续接

已创建的 venv 位于 `/home/unitree/GR00T-WholeBodyControl/.venv_camera`，在线安装因 DNS 失败，尚未安装依赖。恢复有线连接后，先完成 wheel 传输及哈希核验，再在 Orin 使用以下官方包安装方式；不需要改系统 DNS，也不需要 sudo：

```bash
cd /home/unitree/sonic_official_camera_7f151314
uv pip install --python /home/unitree/GR00T-WholeBodyControl/.venv_camera/bin/python \
  --no-index --find-links wheels setuptools wheel pip
uv pip install --python /home/unitree/GR00T-WholeBodyControl/.venv_camera/bin/python \
  --no-index --find-links wheels --no-build-isolation -e 'gear_sonic[camera]' pyrealsense2
```

接着先运行官方相机模块 `--help` 和 SDK 设备枚举。当前不启动相机 systemd 服务，也不填写未知设备编号。

## 真机状态与回滚

本轮获授权后暂停旧自动启动相关进程，通过原终端 O 让旧控制器输出 Kp=0/Kd=8 阻尼退出；被动 DDS 确认后没有持续 LowCmd。随后停止 `unitree_sonic.service`。停止期间附属 docker 客户端未及时退出，服务最终状态为 **failed**，开机设置仍为 **enabled**，没有 disable。

最新可登录核验时没有 G1 控制进程。**当前网线断开，无法复核实时状态；如果 G1 期间重启，enabled 服务可能再次启动原控制器。** 不自动恢复服务，因为旧启动器会发送 Y 并直接进入带力初始化。

自定义试验没有通过真机跟随验收，已停止；本机 `real_teleop/run_trial_controller.sh` 已禁用，Orin `real_trial_20261026/target/release/g1_deploy_real_trial` 已取消执行权限。保留源码、失败日志和原件供追溯。原版真机二进制与源码未覆盖。

回滚本轮官方环境配置：确认相应环境没有进程后，将新 `.venv_data_collection`、Orin 新 `.venv_camera`、`sonic_official_camera_7f151314` 和本目录移至备份目录即可。仿真现有成果不用回滚。恢复旧真机服务属于物理启控，需在现场按其原流程执行，不能作为自动文件回滚的一部分。没有 Git 提交、推送、reset 或 clean。

## 来源

- [SONIC 官方 PICO 教程](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vr_wholebody_teleop.html)
- [SONIC 官方采集教程](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)
- [官方 RealSense 多相机入口源码](https://github.com/NVlabs/GR00T-WholeBodyControl/blob/main/gear_sonic/camera/composed_camera.py)
- [SONIC Dex3 实现](https://github.com/NVlabs/GR00T-WholeBodyControl/blob/main/gear_sonic_deploy/src/g1/g1_deploy_onnx_ref/include/dex3_hands.hpp)
- [Unitree 官方 Dex1 服务](https://github.com/unitreerobotics/dex1_1_service)提供独立 Dex1 接口；它不等于 SONIC 已接通 Dex1。本轮没有启动或安装夹爪控制服务。
