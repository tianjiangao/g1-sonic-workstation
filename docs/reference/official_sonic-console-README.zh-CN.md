> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# SONIC 工作站控制台

**最新更新：** 新增“开始下一轮真机验证（SONIC + Dex1）”，必须确认现场条件才启动。PICO→Dex1控制映射已通过26项测试、隔离DDS及真实SDK读取检查，真实开合尚待现场验收。该按钮启动的是原版SONIC与宇树夹爪控制逻辑；训练数据采集尚未验收。详见 [映射与启动说明](../DEX1映射说明.zh-CN.md)。以下“真机按钮锁定”等是初始版本历史描述，以此更新为准。

从桌面或应用菜单打开 **SONIC 工作站**。也可运行：

```bash
python3 /opt/g1/GR00T-WholeBodyControl/official_sonic/console/app.py
```

这是主机端的薄启动界面，不是新的机器人控制器。不创建 DDS 发布器、不登录机器人、不修改网卡、不调用运动 RPC。只启动固定白名单内的本机作业。真机/实际采集尚未完成验收，所以对应按钮明确锁定，修改配置文件或历史 PASS 记录也不会解锁。

## 现在可用

1. **启动 PICO PC Service**：复用已有服务，没有时调用本机安装的 XRoboToolkit 服务入口。启动成功仅代表 SDK 端口可用，不代表24关节追踪通过。服务是共享组件，关闭控制台不自动停止它。
2. **采集组件自检**：直接调用官方 `Gr00tDataExporter`，生成一个标注 `SYNTHETIC_ONLY` 的测试 episode，保存并回读 Parquet、元数据和三路 MP4。不会连接相机/机器人，不运行运动策略。测试数据位于 `selftests/`，不写入用户设置的真实数据目录。
3. **检查 PICO 数据**：运行现有隔离入口的 probe 模式，检查24关节数据；不启动机器人控制器。需先让 PC Service 启动并连接头显，Full Body/Send 开启、A键切换关闭。
4. **隔离仿真 / 离线仿真自检**：复用 `start_sim_teleop.sh`。全部仿真 DDS 位于仅有 lo 的网络 namespace 中。离线自检15秒后自动结束；正常仿真等待用户停止。
5. **采集设置**：保存 Orin/相机/发布机地址、任务、数据集名称、输出目录和频率。修改前自动备份，坏配置阻止执行；预览只生成 `launch-plan.json`，不启动采集。
6. **运行日志**：每个作业有独立目录、命令参数、PID/启动时间和退出码。关闭控制台会停止本窗口创建的作业；不会停止别的窗口启动的仿真或真实机器人进程。

官方算法、控制状态机和数据格式均未修改。现有 SDK 原子读取适配及仿真专用隔离沿用之前验证的实现。

## 还不能称为一键真机系统

- Dex1 和当前 SONIC Dex3 控制/采集模型之间尚未接通。
- Orin 的 RealSense SDK 已安装且可加载，但当前设备列表为空；两台机器都没有枚举到 D405。
- 多 RealSense 的官方 composed camera 没有传递设备编号，需要先确定可用的上游方案再标定头/左右腕，不能用同一画面冒充三路。
- 原生 PICO 入口的时间戳兼容性和真机失联/停止行为需现场验收。
- 当前 PICO 若仍在192.168.5.x Wi-Fi，本机旧临时192.168.5.250地址已不存在；不能把 SDK 端口可用等同于网络互通。任何物理网卡改动单独征求同意。

## 验证记录

- `evidence/backend-tests.log`：7项设置、输入与作业所有权测试。
- `evidence/gui-smoke.json`、`console.png`：原生界面、状态行、设置回读及真机按钮锁定检查。
- `selftests/SYNTHETIC_ONLY_*/selfcheck-result.json`：官方导出器实际编码/回读结果，明确 `real_robot_verified=false`。
- 隔离仿真本轮日志：`sim_teleop/logs/20261026-162729-304225`，LowCmd 4311、LowState 2858、数值/限位故障0；namespace仅lo，结束后状态stopped。不是本轮真人PICO验收。
- Orin相机安装与USB对比：`../evidence/reconnect/`。

本轮无真实机器人动作测试，没有将设备未连接的项目判定为通过。

## 回滚

先关闭控制台并等待它创建的作业退出。移走 `official_sonic/console/`、`~/.local/share/applications/sonic-workstation.desktop` 和桌面的 `SONIC 工作站.desktop` 即可撤销界面入口；保留 `selftests/` 和日志便于追溯。修改前主说明备份在 `evidence/README.before-console.zh-CN.md`。

相机环境与官方依赖独立保留，界面回滚不会修改它们，也不会改变旧真机服务的 stopped/failed、enabled 状态。PC Service 若仍有其他消费者，不自动停止。未提交或推送 Git。
