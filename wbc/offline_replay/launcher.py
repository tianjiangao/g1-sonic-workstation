"""Optional subprocess launcher. Importing this never loads MuJoCo or SDKs."""
from dataclasses import dataclass
from pathlib import Path
import json,os,subprocess,time,uuid
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=Path('/opt/g1/workspace/reports/offline_replay_runs')
@dataclass
class Handle:
    process:object
    ready:Path
    log:Path
    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
    def wait_ready(self,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if self.ready.exists():return json.loads(self.ready.read_text())
            if self.process.poll() is not None:raise RuntimeError('3D回放进程失败：'+self.log.read_text()[-1500:])
            time.sleep(.1)
        self.stop();raise RuntimeError('3D回放初始化超时；已停止独立显示进程')
def launch(episode):
    run=OUTPUT/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);run.mkdir(parents=True,exist_ok=False);(run/'engineering_only').touch()
    log=run/'viewer.log';ready=run/'ready.json';env=dict(os.environ)
    env.update(MUJOCO_GL='egl',LIBGL_ALWAYS_SOFTWARE='1',__EGL_VENDOR_LIBRARY_FILENAMES='/usr/share/glvnd/egl_vendor.d/50_mesa.json',LP_NUM_THREADS='2',MESA_SHADER_CACHE_DISABLE='true')
    command=[str(ROOT/'.venv_sim/bin/python'),'-m','offline_replay.server','--episode',str(Path(episode).resolve()),'--receipt',str(ready),'--port','0']
    with log.open('ab') as out:p=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True)
    return Handle(p,ready,log)
