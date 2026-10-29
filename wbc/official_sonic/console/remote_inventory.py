"""Explicit user-triggered SSH inventory. No sudo, DDS, RPC or service mutation."""
import argparse
from datetime import datetime
import ipaddress
import json
from pathlib import Path
import subprocess
import time
from official_sonic.console.backend import ConfigStore,BASE
from official_sonic.console.hardware import summarize
from official_sonic.console.ssh_connection import ssh_args

# Fixed, reviewed code; no settings are interpolated into a remote shell.
REMOTE=r'''
import json,subprocess,sys,time
from pathlib import Path
d={"kind":"READONLY_ENUMERATION","remote_monotonic":time.monotonic()}
def command(args):
 try:return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=4).strip()
 except Exception as e:return "ERROR: "+str(e)
d["usb"]=command(["lsusb"])
d["usb_tree"]=command(["lsusb","-t"])
d["video_nodes"]=[str(p) for p in Path("/dev").glob("video*")]
d["unitree_sonic"]={}
for line in command(["systemctl","show","unitree_sonic.service","-p","ActiveState","-p","SubState","-p","UnitFileState"]).splitlines():
 if "=" in line:
  k,v=line.split("=",1);d["unitree_sonic"][k]=v
d["dex1_units"]= [s for s in command(["systemctl","list-units","--all","--no-pager","--no-legend"]).splitlines() if "dex1" in s.lower() or "gripper" in s.lower()]
d["controllers"]=[]
for p in Path("/proc").glob("[0-9]*"):
 try:
  args=(p/"cmdline").read_bytes().split(b"\0")
  exe=Path(args[0].decode()).name
  if exe in ("g1_deploy_onnx_ref","g1_deploy_real_trial"):d["controllers"].append({"pid":int(p.name),"exe":exe})
 except (OSError,UnicodeError):pass
try:
 import pyrealsense2 as rs
 d["camera_devices"]=[{"name":x.get_info(rs.camera_info.name),"serial":x.get_info(rs.camera_info.serial_number)} for x in rs.context().query_devices()]
except Exception as e:d["camera_error"]=str(e)
print(json.dumps(d))
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(BASE/'remote-inventory.json'));a=p.parse_args()
    config=ConfigStore().load();ipaddress.IPv4Address(config.robot_ip)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    report={'observed_at':datetime.now().astimezone().isoformat(timespec='seconds'),
            'host':config.robot_ip,'scope':'只读 OS/USB/SDK枚举，不打开相机流、不发送控制指令'}
    try:
        ssh=ssh_args(config.robot_ip)+[
             'cd /home/unitree/sonic_official_camera_7f151314 && /home/unitree/GR00T-WholeBodyControl/.venv_camera/bin/python -']
        r=subprocess.run(ssh,input=REMOTE,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=18)
        if r.returncode:raise RuntimeError(r.stderr.strip() or f'SSH exit {r.returncode}')
        inventory=json.loads(r.stdout);report.update(result='PASS_READONLY_INVENTORY',inventory=inventory,summary=summarize(inventory))
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
        report.update(result='BLOCKED',error=str(e),hint='SSH自动连接失败；检查网络和工作站专用密钥授权，不在图形界面保存密码。')
    temp=out.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.replace(out)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    if report['result']=='BLOCKED':raise SystemExit(2)

if __name__=='__main__':main()
