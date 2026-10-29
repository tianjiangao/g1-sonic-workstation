"""Supervise official camera processes only; no robot controller is launched."""
import argparse
import json
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import sys
import time
from official_sonic.console.backend import ROOT,BASE,ConfigStore
from official_sonic.console.ssh_connection import ssh_args

def check_viewer_exit(code):
    if code not in (None,0):raise RuntimeError(f'官方相机查看器异常退出：{code}，详见日志')

def camera_args(roles):
    left=roles.get('left_wrist',{});right=roles.get('right_wrist',{})
    if not left.get('confirmed') or not right.get('confirmed') or not left.get('serial') or not right.get('serial') or left['serial']==right['serial']:
        raise ValueError('左右腕相机需要分别确认且序列号不得重复')
    return ['--ego-view-camera','None','--left-wrist-camera','realsense','--left-wrist-device-id',left['serial'],
            '--right-wrist-camera','realsense','--right-wrist-device-id',right['serial'],'--fps','15','--port','5555']

REMOTE=r'''
import os,select,signal,socket,subprocess,sys,time,json
probe=socket.socket();probe.settimeout(.3)
try:
 probe.connect(('127.0.0.1',5555))
except OSError:pass
else:raise SystemExit('Camera port 5555 already owned; refusing to replace existing service')
finally:probe.close()
os.chdir('/home/unitree/sonic_official_camera_7f151314')
args=json.loads(sys.argv[1])
p=subprocess.Popen(['/home/unitree/GR00T-WholeBodyControl/.venv_camera/bin/python','-u','-m','gear_sonic.camera.composed_camera']+args)
print('OWNED_CAMERA_PID',p.pid,flush=True)
try:
 deadline=time.monotonic()+3600
 while p.poll() is None and time.monotonic()<deadline:
  readable,_,_=select.select([sys.stdin.buffer],[],[],.5)
  if readable and not os.read(sys.stdin.fileno(),1):break
finally:
 if p.poll() is None:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 print('OWNED_CAMERA_EXIT',p.returncode,flush=True)
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=0);p.add_argument('--no-view',action='store_true');a=p.parse_args()
    config=ConfigStore().load();roles=json.loads((ROOT/'official_sonic/profiles/camera-roles.json').read_text());args=camera_args(roles)
    if config.camera_ip!=config.robot_ip:raise ValueError('双腕预览使用 Orin 的 camera_ip，须与 robot_ip 一致')
    remote='python3 -u -c '+shlex.quote(REMOTE)+' '+shlex.quote(json.dumps(args))
    ssh=ssh_args(config.robot_ip)+[remote]
    server=None;viewer=None
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        server=subprocess.Popen(ssh,stdin=subprocess.PIPE)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            if server.poll() is not None:raise RuntimeError('远端相机启动失败，查看上方日志')
            try:
                with socket.create_connection((config.camera_ip,5555),timeout=.3):pass
                break
            except OSError:time.sleep(.2)
        else:raise RuntimeError('远端相机端口未就绪')
        if not a.no_view:
            # LeRobot requires opencv-python-headless in its own environment.
            # Reuse the existing GUI-enabled sim env for the unmodified viewer.
            viewer=subprocess.Popen([str(ROOT/'.venv_sim/bin/python'),str(ROOT/'gear_sonic/scripts/run_camera_viewer.py'),
                '--camera-host',config.camera_ip,'--camera-port','5555','--fps','15',
                '--output-path',str(BASE/'camera_previews')],cwd=ROOT)
        start=time.monotonic()
        while server.poll() is None and (viewer is None or viewer.poll() is None):
            if a.seconds and time.monotonic()-start>=a.seconds:break
            time.sleep(.1)
        if server.poll() is not None:raise RuntimeError('远端相机服务意外退出')
        if viewer:check_viewer_exit(viewer.poll())
    except KeyboardInterrupt:print('关闭本次双腕预览',flush=True)
    finally:
        if viewer and viewer.poll() is None:
            viewer.terminate()
            try:viewer.wait(timeout=4)
            except subprocess.TimeoutExpired:viewer.kill();viewer.wait()
        if server:
            # EOF makes the remote supervisor stop only the child it created.
            if server.stdin:server.stdin.close()
            try:server.wait(timeout=12)
            except subprocess.TimeoutExpired:server.terminate();server.wait(timeout=4)

if __name__=='__main__':main()
