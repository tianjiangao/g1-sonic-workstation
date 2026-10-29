"""Start/reuse the reviewed SONIC camera server. Never starts motor services."""
import json,subprocess,tempfile,os,sys
from pathlib import Path
from official_sonic.console.backend import ROOT,ConfigStore
from official_sonic.console.ssh_connection import ssh_args
REMOTE=r'''
import json,subprocess,sys,time,socket
from pathlib import Path
base=Path('/home/unitree/sonic_official_camera_7f151314')
pids=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=(p/'cmdline').read_bytes().split(b'\0')
  if b'gear_sonic.camera.composed_camera' in args:
   if (p/'cwd').resolve()!=base:raise RuntimeError('Camera module is running from another checkout; refusing to replace it')
   pids.append(int(p.name))
 except OSError:pass
if len(pids)>1:raise RuntimeError('Multiple camera servers; inspect before restarting')
unit=Path.home()/'.config/systemd/user/sonic-three-camera.service'
managed=unit.is_file()
if not pids and managed:
 r=subprocess.run(['systemctl','--user','start','sonic-three-camera.service'],capture_output=True,text=True,timeout=8)
 if r.returncode:raise RuntimeError('Camera login service failed: '+r.stderr[-1200:])
 print(json.dumps({'service':'sonic-three-camera.service','body_control_started':False,'dex1_service_modified':False}))
 sys.exit(0)
if not pids:
 probe=socket.socket();probe.settimeout(.3)
 try:probe.connect(('127.0.0.1',5555))
 except OSError:pass
 else:raise RuntimeError('Camera port 5555 is owned by an unknown service; refusing to replace it')
 finally:probe.close()
 log=base/'evidence/console-migration/desktop-camera.log';log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('ab') as out:
  child=subprocess.Popen(['bash',str(base/'start_three.sh')],cwd=base,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True)
 time.sleep(.3)
 if child.poll() is not None:raise RuntimeError('SONIC camera startup failed; see '+str(log))
 pids=[child.pid]
print(json.dumps({'sonic_camera_pids':pids,'body_control_started':False,'dex1_service_modified':False}))
'''
def ensure(config):
 cmd=ssh_args(config.camera_ip)+['python3 -']
 r=subprocess.run(cmd,input=REMOTE,capture_output=True,text=True,timeout=12)
 if r.returncode:raise RuntimeError('SONIC相机启动检查失败：'+r.stderr[-1200:])
 result=json.loads(r.stdout)
 print('检查SONIC三路相机实际图像（不启动身体）……',flush=True)
 with tempfile.TemporaryDirectory(prefix='sonic-camera-check-') as cache:
  env=dict(os.environ,PYTHONPATH='/opt/g1/workspace')
  r=subprocess.run([str(ROOT/'.venv_sim/bin/python'),'-m','capture.live_view','--host',config.camera_ip,'--cache',cache,'--seconds','35','--once'],env=env,capture_output=True,text=True,timeout=40)
  if r.returncode:raise RuntimeError('SONIC三路图像未就绪，身体未启动：'+r.stderr[-1000:])
  result['live_frames']=json.loads((Path(cache)/'status.json').read_text())
 return result
if __name__=='__main__':
 try:print(json.dumps(ensure(ConfigStore().load()),ensure_ascii=False))
 except Exception as e:print(str(e),file=sys.stderr);sys.exit(2)
