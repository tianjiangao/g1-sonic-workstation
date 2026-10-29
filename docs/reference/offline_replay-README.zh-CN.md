> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# G1 + Dex1 离线 MuJoCo 回放

本模块已实现：读取本机已结束 Episode 的真实29D机器人反馈与左右各1D夹爪电机反馈，按名称写入独立被动模型；统一时间轴显示保存图像和关节曲线。机器人可以关机。不会启动策略、物理步进、DDS、ZMQ或电机控制。

## 启动

工作站下次打开后新增「3D / 回放」页：选择已保存片段 → 打开独立3D回放。显示进程可单独关闭。已有工作站窗口不会自动热加载代码，重新打开即可看到该页。

也可以在工程根目录直接运行（终端保留，Ctrl-C仅关闭自己的显示进程）：

```bash
cd /opt/g1/GR00T-WholeBodyControl
.venv_sim/bin/python -m offline_replay.demo --episode outputs/real_sessions/g1_demo/SESSION_20261028_095554_231880/episode_000000
```

打开输出的localhost URL。支持暂停、0.25/0.5/1/2/4倍速、时间轴、全身/左右夹爪近景、视角、反馈/目标角切换。使用现有MuJoCo3.14.0和OpenCV环境，无新增依赖。默认Mesa CPU渲染、低进程优先级、两线程上限、单请求服务与一个待显示帧；显示可丢帧，不处理采集线程。只绑定127.0.0.1动态端口，拒绝5555/5556/5557。日志/哈希收据在`/opt/g1/workspace/reports/offline_replay_runs`，标记engineering_only。

## 模型与兼容边界

当前选择由`model_config.json`指向`assets_dex1_v3`：

- `g1_sonic_dex1.xml`：29本体铰链+4指滑动关节，33执行器。保留原本体29个执行器的顺序。
- `g1_sonic_dex1_passive.xml`：相同结构，删除全部执行器，UI只加载此版本。free joint +29hinges+4slides，因此nq=40、nv=39、nu=0。
- `build-report.json`：模型、全部Mesh哈希，来源、腕部连接和限位、质量惯量记录。

本体来自本机SONIC `gear_sonic_deploy/g1/g1_29dof.xml`，Mesh复用SONIC已有完整资产（部署目录中的LFS指针不能作为Mesh）。左右腕末端替换为Dex1；腕部惯量采用参考URDF的裸腕定义，避免保留含原手掌的质量后重复加装夹爪。所有29个本体关节的名称、局部坐标、轴、限位与原43DoF资产逐项对照。

原入口`gear_sonic/scripts/run_sim_loop.py`和原`scene_43dof.xml`保持原状。原`base_sim.py`含每手7DoF Dex3假设，**新33DoF XML不是旧控制循环的直接替换文件**。本次验收为被动运动学回放；未启动旧仿真循环、策略、接触抓取或全身动力学验收。

`build_model.py`是本地审查后编写的提取器，不执行下载的构建脚本。可输出到全新目录，拒绝覆盖已有目录：

```bash
.venv_sim/bin/python -m offline_replay.build_model --output /tmp/g1_dex1_new_build
```

早期`assets/`、`assets_dex1_v2/`及报告保留为实验记录；v3修复原XML多个worldbody中的重复地面，禁止将早期截图当最终验收。

## 状态与单位合同

| 数据 | 语义/单位 | 回放处理 |
| --- | --- | --- |
| `observation.body` | 实际29D关节角，rad | 与原始g1_debug同receipt的body_q核对；缺失则失败 |
| `action.body` | SONIC已缩放加偏置的last_action目标角，rad | 单独标注，不能补实际反馈 |
| PICO/SMPL | 人体姿态 | 不作为机器人关节角 |
| SONIC64D token | 策略latent动作 | 不作为29D关节角 |
| `observation.dex1` | 物理左、右电机反馈各1D，rad | 原始维度仍为2 |
| `action.dex1` | 物理左、右电机目标各1D，rad | 与反馈分开；目标模式使用命令 |
| 模型4slides | 各手两个相反轴的指滑动位移，m | 仅用于显示，不导出为真实4D动作 |

G1角度来自部署输出已完成IsaacLab→MuJoCo重排的body_q；不能再次重排或加默认角。body_q_target不是本模块目标来源。每帧按主机monotonic记录网格选择，时间严格递增；三路保存图像中头部左右目分开显示为四个光学视图。这证明共用记录时间轴，不证明相机曝光硬同步。无可靠全球基座位姿，固定freebase，只显示相对关节运动。

`GripperStateAdapter`按名称将每侧0..5.4rad名义映射为两个相反轴滑动关节的-0.020..0.0245m；小范围编码器超调仅在显示端裁剪并返回标志，原始值保留。**尚未标定实物电机角到毫米间距的关系**。URDF限位下参考说明闭合仍约5.88mm垫间隙；未采用社区MJCF额外-0.023m闭合修正。不能据此宣称与实物夹紧间隙/受力一致。

## 静态隔离验收

```bash
env SONIC_HOST_NETNS="$(readlink /proc/self/ns/net)" unshare --user --map-root-user --net .venv_sim/bin/python -m offline_replay.validate_model --output /tmp/dex1_validation_new
.venv_sim/bin/python -m unittest discover -s offline_replay/tests -v
env PYTHONPATH=external_dependencies/unitree_sdk2_python .venv_sim/bin/python -m unittest discover -s official_sonic/console/tests -q
```

输出必须为全新目录。验证脚本要求不同的network namespace、仅lo、机器人IP无路由；检查模型、29本体映射、正惯量、相反滑动轴、URDF限位；左右独立开闭、101帧SYNTHETIC_ONLY序列写出后读回并映射、近景/全身截图、指间深穿透检查。这里只检查所列状态的指间接触，不能替代全机器人碰撞/力学验证。

最终记录见本模块`report-root.txt`指向目录的`dex1-final-validation/result.json`。新增11项数据/映射/进程测试通过；工作站原93项回归通过。裸系统Python或未设置本地SDK路径的环境会缺msgpack/SDK，不作为正确测试环境。进程测试覆盖正常退出及强制崩溃后原始Episode哈希保持；退出收据记录raw_unchanged。没有执行任何真实机器人动作验收。

## 来源与许可证

- NVIDIA官方[sim2sim快速开始](https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/quickstart.html)、[数采指南](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)。官方支持MuJoCo仿真及数据流程；本模块是本地增加的审核工具，不声称为官方清洗模块。
- Unitree官方[xr_teleoperate](https://github.com/unitreerobotics/xr_teleoperate)、[unitree_sim_isaaclab](https://github.com/unitreerobotics/unitree_sim_isaaclab)、[unitree_ros](https://github.com/unitreerobotics/unitree_ros)。真实Dex1桥接保持本机既有实现与版本。
- 社区[unitree-g1-mujoco](https://huggingface.co/lerobot/unitree-g1-mujoco/tree/68459ed68f6f68e1f661091dfcb6ebce44681aec)，锁定commit `68459ed68f6f68e1f661091dfcb6ebce44681aec`。下载清单/sha256在`vendor/dex1_reference/download-manifest.json`。模型卡未统一声明资产许可证；hiw500子参考含Apache2.0不能扩展推定整个资产包均为Apache。本地验证保留来源，分发前需补许可证审核。

## 对数采与清洗的作用

值得保留离线回放：可帮助人工发现左右手映射错误、实际反馈停滞、命令与反馈偏离、图像/姿态错位、短片段和不完整记录。它不会修复缺失真实反馈、补造token、判断抓取成功或自动批准片段。正式清洗继续走已锁定的人工审核→官方导出/清洗→读取器/哈希验收流程；不得单独删除重复视频帧。实时镜像/Rerun只形成下一阶段方案，见`REALTIME_DESIGN.md`。

回滚：删除工作站`app.py`中的ReplayPanel导入和独立页注册两处新增内容即可禁用入口；无需改变控制器。任务前的app.py保存在报告backup中，但其中可能有用户后续编辑，不应整文件覆盖回滚。
