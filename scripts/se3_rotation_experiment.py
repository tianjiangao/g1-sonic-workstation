#!/usr/bin/env python3
"""Read G1's MuJoCo root pose and verify SE(3) point round trips."""

import argparse
import math
from pathlib import Path

import mujoco
import numpy as np


DEFAULT_SCENE = Path.home() / "unitree_mujoco/unitree_robots/g1/scene.xml"
DEFAULT_REPORT = Path(__file__).resolve().parent.parent / "docs/se3_rotation_experiment.md"
POINTS_WORLD = {
    "P1": np.array([2.0, 0.0, 1.0]),
    "P2": np.array([2.3, 1.2, 1.4]),
    "P3": np.array([-1.1, 2.4, 0.6]),
}


def read_pose(data, body_id):
    """Read MuJoCo's world pose of the pelvis body after mj_forward."""
    t = data.xpos[body_id].copy()
    q = data.xquat[body_id].copy()  # MuJoCo: w, x, y, z
    r = data.xmat[body_id].reshape(3, 3).copy()
    transform = np.eye(4)
    transform[:3, :3] = r
    transform[:3, 3] = t
    return t, q, r, transform


def fmt_array(values):
    return np.array2string(
        np.asarray(values),
        formatter={"float_kind": lambda value: f"{value: .9f}"},
    )


def fmt_vec(values):
    return "(" + ", ".join(f"{value:.9f}" for value in values) + ")"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    model = mujoco.MjModel.from_xml_path(str(args.scene.resolve()))
    data = mujoco.MjData(model)
    root_joint = model.joint("floating_base_joint")
    body_id = model.body("pelvis").id
    qpos_addr = int(root_joint.qposadr[0])
    if model.jnt_type[root_joint.id] != mujoco.mjtJoint.mjJNT_FREE:
        raise RuntimeError("floating_base_joint is not a free joint")

    mujoco.mj_forward(model, data)
    initial = read_pose(data, body_id)

    # Apply a +90 degree rotation about the world Z axis to the free root.
    yaw_quat = np.array([math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)])
    rotated_quat = np.empty(4)
    mujoco.mju_mulQuat(rotated_quat, yaw_quat, data.qpos[qpos_addr + 3 : qpos_addr + 7])
    data.qpos[qpos_addr + 3 : qpos_addr + 7] = rotated_quat
    mujoco.mj_forward(model, data)
    rotated = read_pose(data, body_id)

    relative_r = rotated[2] @ initial[2].T
    actual_yaw_deg = math.degrees(math.atan2(relative_r[1, 0], relative_r[0, 0]))
    quat_matrix_errors = []
    for pose in (initial, rotated):
        r_from_quat = np.empty(9)
        mujoco.mju_quat2Mat(r_from_quat, pose[1])
        quat_matrix_errors.append(float(np.max(np.abs(r_from_quat.reshape(3, 3) - pose[2]))))

    point_rows = []
    errors = []
    local_deltas = []
    for label, point_world in POINTS_WORLD.items():
        locals_and_recovered = []
        for t, _, r, transform in (initial, rotated):
            point_base = r.T @ (point_world - t)
            point_base_h = np.append(point_base, 1.0)
            point_recovered_h = transform @ point_base_h
            point_recovered = point_recovered_h[:3]
            error = float(np.linalg.norm(point_recovered - point_world))
            locals_and_recovered.append((point_base, point_recovered, error))
            errors.append(error)
        cross_error = float(
            np.linalg.norm(locals_and_recovered[0][1] - locals_and_recovered[1][1])
        )
        local_delta = float(
            np.linalg.norm(locals_and_recovered[0][0] - locals_and_recovered[1][0])
        )
        errors.append(cross_error)
        local_deltas.append(local_delta)
        point_rows.append((label, point_world, *locals_and_recovered, cross_error))

    max_error = max(errors)
    max_quat_r_error = max(quat_matrix_errors)
    position_delta = float(np.linalg.norm(rotated[0] - initial[0]))
    checks = {
        "yaw change is +90 degrees": abs(actual_yaw_deg - 90.0) < 1e-9,
        "root translation is unchanged": position_delta < 1e-12,
        "quaternion agrees with xmat": max_quat_r_error < 1e-12,
        "local point coordinates change": min(local_deltas) > 1e-6,
        "world round-trip and cross-pose error": max_error < 1e-10,
    }
    passed = all(checks.values())

    lines = [
        "# G1 坐标系与 SE(3)：root yaw 旋转 90° 实验",
        "",
        "## 环境与方法",
        "",
        f"- 官方仓库：`{args.scene.resolve().parents[2]}`；场景：`{args.scene.resolve()}`。",
        f"- MuJoCo Python 版本：`{mujoco.__version__}`；模型 `nq={model.nq}`、`nv={model.nv}`。",
        "- 使用 G1 29-DOF 场景的 `floating_base_joint` 和 `pelvis` body。先 `mj_forward`，读取 `data.xpos[body_id]`、`data.xquat[body_id]`、`data.xmat[body_id]`；也可由 `data.qpos[qpos_addr:qpos_addr+7]` 读取 free joint 的位置和四元数。",
        "- 将 root free joint 的姿态左乘绕 world Z 轴 +90° 的四元数，再次 `mj_forward` 并读取 pose。未推进物理时间；这是受控的坐标变换实验，不是机器人动力学转身或 SLAM。",
        "- 三个点是 world frame 中固定的虚拟墙角/地标；未加入场景几何或传感器。单位为米，四元数顺序为 MuJoCo 的 `(w, x, y, z)`。",
        "",
        "## Pose 读数",
        "",
    ]
    for title, (t, q, r, transform) in (
        ("初始", initial),
        ("root yaw +90° 后", rotated),
    ):
        lines += [
            f"### {title}",
            "",
            f"- translation `t = {fmt_vec(t)}`",
            f"- quaternion `q = {fmt_vec(q)}`",
            "- rotation matrix `R`:",
            "",
            "```text",
            fmt_array(r),
            "```",
            "",
            "- homogeneous transform `^W T_B`:",
            "",
            "```text",
            fmt_array(transform),
            "```",
            "",
        ]
    lines += [
        f"实际相对 yaw：`{actual_yaw_deg:.9f}°`；平移变化：`{position_delta:.3e} m`。",
        "",
        "## world 固定点与坐标往返",
        "",
        "计算 `p_B = (^W T_B)^−1 p_W`，再用 `p_W' = ^W T_B p_B` 恢复。下表的点坐标省略齐次分量 1；误差为 3D 欧氏距离。",
        "",
        "| 点 | world 原值 | 初始 base | 旋转后 base | 初始恢复 world | 旋转后恢复 world | 两次恢复差 (m) |",
        "|---|---|---|---|---|---|---:|",
    ]
    for label, point_world, before, after, cross_error in point_rows:
        lines.append(
            f"| {label} | {fmt_vec(point_world)} | {fmt_vec(before[0])} | "
            f"{fmt_vec(after[0])} | {fmt_vec(before[1])} | "
            f"{fmt_vec(after[1])} | {cross_error:.3e} |"
        )
    lines += [
        "",
        f"最大单次往返或两次恢复误差：`{max_error:.3e} m`；阈值：`1e-10 m`。",
        f"四元数转换为矩阵与 `xmat` 的最大元素误差：`{max_quat_r_error:.3e}`。",
        "",
        "## 原理",
        "",
        "`^A T_B` 表示 **B frame 到 A frame** 的刚体坐标变换：它描述 B 的原点和轴在 A 中的位置与方向。这里 `^W T_B` 是 G1 pelvis/base 相对于 world 的 pose。",
        "",
        "对齐次列向量，`p_A = ^A T_B p_B` 表示同一物理点的 B 坐标转换成 A 坐标。`^A T_B = [[R, t], [0, 1]]`，所以普通 3D 坐标满足 `p_A = R p_B + t`。`R` 旋转坐标轴方向，`t` 把 B 原点移到 A 中的位置；逆变换为 `p_B = R^T(p_A - t)`。",
        "",
        "机器人原地转 90° 后，base 坐标轴也转了，因此固定世界点相对于这些轴的分量改变。使用**对应时刻**的 `^W T_B` 把各自的局部坐标转回 world/map frame，同一固定点仍在原处；其数值差仅来自浮点运算。",
        "",
        "单位四元数 `q` 和 3×3 旋转矩阵 `R` 是同一个 3D 旋转的两种表示；本实验从 `xquat` 转出的矩阵与 `xmat` 交叉核对。SE(3) 在旋转之外再加入平移 `t`，用 4×4 齐次矩阵同时表达两者。四元数 `q` 与 `-q` 表示相同旋转。",
        "",
        "## 复现与验收",
        "",
        "```bash",
        "cd /opt/g1/workspace",
        "/opt/g1/user/venvs/g1_brain/bin/python scripts/se3_rotation_experiment.py",
        "```",
        "",
        "官方 Python 仿真器入口为 `cd /opt/g1/user/unitree_mujoco/simulate_python && python3 unitree_mujoco.py`，由 `config.py` 选择机器人和场景；当前配置是 Go2。C++ 入口在构建后的 `simulate/build/unitree_mujoco`，可用 `-r g1 -s scene.xml` 选择 G1，但当前仓库没有 `simulate/build`。本实验直接加载同一官方 G1 MJCF，避免改动配置；现有 `g1_brain` 环境有 MuJoCo，却缺少官方 Python 启动器所需的 `unitree_sdk2py`，因此未验证带 DDS/GUI 的完整仿真器启动。",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    for label, ok in checks.items():
        lines.append(f"| {label} | {'PASS' if ok else 'FAIL'} |")
    lines += ["", f"**总结果：{'PASS' if passed else 'FAIL'}**", ""]

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")
    print(f"relative yaw: {actual_yaw_deg:.9f} deg")
    print(f"max world error: {max_error:.3e} m")
    print(f"quaternion/matrix error: {max_quat_r_error:.3e}")
    print(f"report: {args.report.resolve()}")
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
