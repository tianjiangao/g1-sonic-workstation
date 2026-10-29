#!/usr/bin/env bash
set -u
# Run on G1. Passive inspection only; never starts/stops a controller.
date -Is
ip -br addr
ps -eo pid,ppid,etime,comm,args | grep -E '[g]1_deploy_onnx_ref|[p]ico_manager_thread_server|[m]onitor_fsm.sh'
systemctl show unitree_sonic.service -p ActiveState -p SubState -p UnitFileState
ss -lnt | grep -E ':5556|:5557' || true
docker inspect --format 'image={{.Image}} network={{.HostConfig.NetworkMode}}' g1-deploy-dev
docker exec g1-deploy-dev bash -c 'source /opt/ros/humble/setup.bash; ldd /workspace/g1_deploy/target/release/g1_deploy_onnx_ref | grep "not found" && exit 1; p=$(pgrep -x g1_deploy_onnx_ | head -1); if [ -n "$p" ]; then grep -m1 "libnvinfer.so.10.7.0" /proc/$p/maps; fi'
