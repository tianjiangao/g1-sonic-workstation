> 历史集成参考（已脱敏）。地址、旧状态和报告路径不能直接用于你的机器；请先读主安装指南、WORKFLOW 与 VALIDATION。部分私有证据/报告和资产未分发。

# 本机数据准备 → SSH交付 → 远端训练

当前固定流程：本机数采 → 人工回放审核 → 真实64D SONIC token＋左右各1D Dex1转换 → 官方清洗 → 数据验收 → 规定两跳SSH上传 → 远端训练。

本工具不启动机器人、夹爪或相机控制，不使用下载目录中的MCAP旧转换器，不安装或替换依赖。现有工作台的“导出最近保存段”仍是旧29D诊断导出；**正式数据请用本页的token流程**。录制入口、映射、声音和控制器保持原样。

以下命令均在`/opt/g1/workspace`执行。目标新目录已存在时拒绝覆盖；不要靠删除原始数据来重跑。

## 1. 建立待审核清单并回放

```bash
./pipeline.sh inventory --raw /opt/g1/GR00T-WholeBodyControl/outputs/real_sessions/g1_demo --output /opt/g1/workspace/datasets/reviews/new_inventory.json
./pipeline.sh review-page --manifest /opt/g1/workspace/datasets/reviews/new_inventory.json --output /opt/g1/workspace/reports/new_review
```

在本机浏览器打开新目录的index.html，可以选择episode、播放或拖动原始帧，查看双目头部、物理左右腕和Dex1观测/命令。页面使用原录制帧的接收时间间隔，不把15Hz抽样称为传感器曝光同步。页面只展示，不会改审核清单。

已有本轮9条试录的回放：`reports/local_workflow_20261027/review/index.html`。全部仍为unreviewed。

人工决定后用review命令写**新文件**，例如记录设备测试：

```bash
./pipeline.sh review --manifest /opt/g1/workspace/datasets/reviews/new_inventory.json --output /opt/g1/workspace/datasets/reviews/reviewed_v2.json --episode '/绝对路径/SESSION_实际session/episode_000000' --decision device_test --reviewer '实际审核人' --note '实际设备测试观察' --split unassigned
```

decision可选approved、failed、device_test、pending。只有人工实际看过并确认目标任务成功才选approved，且必须指定train/validation/test。每次审核以上一个新清单为输入，再产生新版本；整段session只能属于一个集合。不完整/源哈希变化会拒绝批准。裁剪可选`--trim-start-s`与`--trim-end-s`，单位秒，不改变原始记录。

## 2. 正式数据：转换、清洗、验收

这一步需要已经人工批准的manifest；没有批准条目会失败，不会自动使用试录。

```bash
./pipeline.sh local-run --manifest /opt/g1/workspace/datasets/reviews/reviewed_v2.json --split train --output /opt/g1/workspace/datasets/task_v001_train
./pipeline.sh local-run --manifest /opt/g1/workspace/datasets/reviews/reviewed_v2.json --split validation --output /opt/g1/workspace/datasets/task_v001_validation
```

每次运行新建converted和cleaned目录；official Gr00tDataExporter导出，再调用固定源码process_dataset.py，显式关闭零SMPL清洗。必要流按工作站monotonic做as-of恢复，缺失/非有限/过期会失败。头部原始双目保留在raw，训练图像按既有约定取左目640×480，左右腕保持物理映射。

cleaned内全量检查低维列/时间/任务索引，三路视频逐帧解码并核对PTS/帧数/尺寸/FPS，再用真实Isaac-GR00T读取器检查起中末训练窗口。状态1×34D、动作40×66D。物理语义和任务成功仍依赖人工审核，程序不代替人判断。

验收成功生成dataset-acceptance.json，绑定全部数据、审核快照、清洗provenance、reader报告的SHA-256。后续多一个文件、修改任何已绑定内容、出现软链接都会拒绝交付。已验收数据再validate只核对旧收据，不重写收据给变化内容重新背书。

分步排查也可用prepare、clean、validate、accept；`./pipeline.sh 命令 --help`查看参数。已验收目录不要添加临时日志，日志存放在外层run目录或reports。

## 3. 工程验证：不批准、不训练

```bash
./pipeline.sh local-run --engineering-episode '/实际完整试录episode绝对路径' --output /opt/g1/workspace/reports/NEW_ENGINEERING_ONLY
```

明确生成engineering_only=true、human_approved=false、formal_training_eligible=false。长度不足41个50Hz点也会拒绝；不能补帧或伪造动作。它可以验证转换/清洗/读取工程，但不能建立正式训练集或说明抓取成功。

## 4. 验收后通过SSH交付

正式训练和验证集分别上传：

```bash
./pipeline.sh upload --dataset /opt/g1/workspace/datasets/task_v001_train/cleaned --receipt-output /opt/g1/workspace/reports/task_v001_train_handoff.json
./pipeline.sh upload --dataset /opt/g1/workspace/datasets/task_v001_validation/cleaned --receipt-output /opt/g1/workspace/reports/task_v001_validation_handoff.json
```

固定路线：本机→jump-user@192.0.2.10→跳板机内SSH unitree@192.0.2.20。复用已有认证与jump.sock，不读取/保存密码或私钥；认证过期时保持本地可恢复状态，不自动改认证或使用ProxyJump替代。

正式包位于远端固定根目录`datasets/accepted/<dataset_id>`。数据先在唯一.partial目录接收，逐文件核对SHA-256后原子发布；失败保留.partial作为恢复证据，不视为已交付。相同内容重传返回already_present，不同内容拒绝覆盖；重试会创建新的partial；先在固定远端命名空间内寻找哈希完全一致的已有文件（含失败partial），独立复制已核验字节，仅补传其余文件，不改动旧副本或自动清理失败证据。探测前同样检查解析后的路径没有越出固定远端根目录。本机源文件始终保留。

工程数据必须显式加`--engineering`，只进入`datasets/engineering/<dataset_id>`，正式上传默认拒绝。旧`python -m sonic_pipeline.sync_raw`已禁用，不再绕过本机验收上传原始片段。

## 5. 远端训练仍有独立门禁

上传只交付文件，不启动训练。远端验收收据通过后还需人工审核的独立训练/验证集、锁定基座与训练环境、8×L40S且每卡至少35GiB空闲；缺任何条件仍停止。正式训练入口先核对收据再检查GPU，不重新验收已变更数据。现有试录的远端正式训练拒绝已经实际复验。

## 环境与回滚

本机复用现有WBC `.venv_data_collection`和Isaac-GR00T `.venv`。转换/清洗/reader执行前会校验固定HEAD及相关官方源码的Git对象哈希，保留不相关的已有控制补丁；验收绑定各阶段一致的源码版本。训练与验证必须分别声明train/validation，且源session或原始内容指纹重叠均会拒绝。转换/清洗/reader subprocess均隐藏CUDA设备，离线处理不加载VLA模型。本次没有安装依赖。

本轮本机备份与SHA-256：`reports/local_workflow_20261027/backup`、`backup-manifest.json`。远端策略/门禁原件：固定根目录`reports/local_workflow_20261027_backup`。恢复应先核对备份哈希并在无数据任务运行时恢复整组规范、contract、policy-lock及代码；新增文件先归档，不删除原始数据、审核、失败证据或验收数据。回滚旧规范也属于明确修订，须有用户授权，不能擅自改回旧流程。

官方参考：[数采与Exporter](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/data_collection.html)、[VLA流程](https://nvlabs.github.io/GR00T-WholeBodyControl/tutorials/vla_workflow.html)。使用的是锁定本机源码，不自动追随网站版本更新。
