"""Operator-started SONIC + pinned Unitree Dex1 mapping, no custom WBC policy."""
import argparse
from datetime import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import pty
import shlex
import signal
import subprocess
import sys
import time
from official_sonic.console.backend import ROOT,BASE,ConfigStore,capture_command
from official_sonic.console.ssh_connection import ssh_args as robot_ssh_args,wait_for_connection
from official_sonic.startup_status import StartupStatus
from official_sonic.thermal_monitor import finite

HEALTH_HOLD_PATH=ROOT/'official_sonic/health_hold.json'

def verify_health_hold():
    """Block a new session on unresolved evidence; never command a live robot."""
    if not HEALTH_HOLD_PATH.exists():return
    try:
        record=json.loads(HEALTH_HOLD_PATH.read_text())
        if not isinstance(record,dict) or type(record.get('blocked')) is not bool:
            raise ValueError('invalid blocked flag')
    except (OSError,ValueError) as e:
        raise RuntimeError('机器人健康记录不可用；拒绝启动真机遥操：'+str(e)) from e
    if record['blocked']:
        raise RuntimeError('热安全暂缓：'+record.get('reason','存在尚未排查的热故障')+
            '。未启动控制器、未释放运控。降温或升级模型不能自动解除；需排查并验收后更新健康记录。报告：'+record.get('report',''))

def console_control_line(line):
    """Compact only console copies; raw controller logs stay byte-for-byte."""
    text=line.strip();low=text.lower()
    if any(word in low for word in ('error','warn','timeout','invalid','nonfinite','safety','emergency','stop','start','init','mode','switch','overflow','gap')):return True
    return not text.startswith(('[ZMQEndpointInterface]','[StreamedMotionMerger]','Frame['))

class ChildLogRelay:
    """Expose child failures and progress in the console's existing log tab."""
    def __init__(self,run,progress=None):self.run=run;self.offsets={};self.progress=progress;self.pending={};self.filtered=0
    def poll(self):
        for name in ('official-controller','pico-streamer','dex1-mapping','capture'):
            path=self.run/(name+'.log')
            if not path.exists():continue
            with path.open('rb') as f:
                f.seek(self.offsets.get(name,0));chunk=f.read();self.offsets[name]=f.tell()
            if chunk:
                text=chunk.decode(errors='replace').replace('\r','')
                if name=='official-controller' and self.progress:self.progress.feed(text)
                if name=='official-controller':
                    pieces=(self.pending.get(name,'')+text).splitlines(keepends=True);self.pending[name]=''
                    if pieces and not pieces[-1].endswith('\n'):self.pending[name]=pieces.pop()
                    shown=[]
                    for line in pieces:
                        if console_control_line(line):shown.append(line)
                        else:self.filtered+=1
                    text=''.join(shown)
                if text:print('['+name+'] '+text,flush=True)
    def flush(self):
        for name,text in self.pending.items():
            if text:print('['+name+'] '+text,flush=True)
        self.pending.clear()
        if self.filtered:print(f'控制台已折叠 {self.filtered} 行逐帧调试输出；完整原文保留于 {self.run}/official-controller.log',flush=True)

class NormalSessionEnd(Exception):pass

def check_child_health(children,reported):
    for name,child in children:
        if name in ('pico-streamer','official-controller') and child.poll()==0:
            raise NormalSessionEnd(name+' 正常停止，结束本次会话')
    notices=[]
    for name,child in children:
        code=child.poll()
        if code is None:continue
        if name in ('dex1-mapping','capture'):
            if name not in reported:
                notices.append((name,code));reported.add(name)
        else:raise RuntimeError(f'{name} 已退出，代码 {code}；正在结束本次会话')
    return notices

def ssh_args(config):
    return robot_ssh_args(config.robot_ip)

def remote_action(config,action):
    source=(ROOT/'official_sonic/console/remote_prepare.py').read_text()
    r=subprocess.run(ssh_args(config)+['python3 - '+shlex.quote(action)],input=source,text=True,capture_output=True,timeout=120)
    if r.returncode:raise RuntimeError('启动检查未通过：'+r.stderr.strip())
    return json.loads(r.stdout)

def startup_actions(d):
    if d['controllers']:raise RuntimeError('已有身体控制器，不能重复启动；请用「仅启动数采」')
    if d['autostart'] not in ('inactive','failed'):raise RuntimeError('机器人自动启动器仍运行，拒绝争用控制权')
    if len(d['dex1_pids'])>1:raise RuntimeError('检测到多个Dex1服务，拒绝重复启动')
    actions=[]
    if not d['container_running']:actions.append('prepare_container')
    if not d['dex1_pids']:actions.append('start_dex1')
    return actions

def validate_dds_probe(data):
    if not data:raise RuntimeError('DDS检查未返回数据；未启动身体控制器')
    d=data[-1]
    if d['lowcmd_count']:
        raise RuntimeError(f"身体控制权冲突：检测到 {d['lowcmd_count']} 条 LowCmd；LowState {d['lowstate_count']} 条，年龄 {d['state_age_s']:.4f}s。即使命令增益为零也不能忽略；请先确认现有命令源已正常退出。")
    if d['lowstate_count']<50 or not math.isfinite(d['state_age_s']) or not 0<=d['state_age_s']<=.1:
        raise RuntimeError(f"LowState反馈不足/过期：{d['lowstate_count']} 条，年龄 {d['state_age_s']:.4f}s；未启动身体控制器")
    temperatures=d.get('temperature_C');errors=d.get('motor_errors')
    if not finite(temperatures,58) or any(not -40<=v<=180 for v in temperatures) or not finite(d.get('state_q'),29):
        raise RuntimeError('LowState温度/关节反馈缺失或无效；未启动身体控制器')
    if not isinstance(errors,list) or len(errors)!=29 or any(type(v) is not int or v!=0 for v in errors):
        raise RuntimeError('LowState电机故障字段异常；未启动身体控制器')
    # Entry check uses the existing SONIC alarm-clear boundary, not a gain change.
    if max(temperatures)>=85:raise RuntimeError(f'启动前电机温度仍偏高：{max(temperatures)}°C（须低于85°C）；未启控，降温不能自动解除历史热异常')
    return {'lowcmd_count':d['lowcmd_count'],'lowstate_count':d['lowstate_count'],'state_age_s':d['state_age_s'],'temperature_peak_C':max(temperatures),'motor_errors':errors}

def body_dds_check(config,run=None):
    profile=json.loads((ROOT/'official_sonic/profiles/passive-health-poll.json').read_text())
    binary=profile['container_binary'];digest=profile['binary_sha256']
    if not binary.startswith('/workspace/g1_deploy/diagnostics/readonly_health_v1_') or '..' in binary or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise RuntimeError('只读探针配置无效；未启动控制器')
    checker='from pathlib import Path; import hashlib,subprocess; p=Path('+repr(binary)+'); assert hashlib.sha256(p.read_bytes()).hexdigest()=='+repr(digest)+', "Read-only probe hash mismatch"; raise SystemExit(subprocess.run([str(p)],timeout=5).returncode)'
    probe='docker exec g1-deploy-dev env LD_LIBRARY_PATH=/workspace/g1_deploy/thirdparty/unitree_sdk2/thirdparty/lib/aarch64 python3 -c '+shlex.quote(checker)
    r=subprocess.run(ssh_args(config)+[probe],text=True,capture_output=True,timeout=8)
    if run is not None:(run/'dds-before.jsonl').write_text(r.stdout)
    if r.returncode:raise RuntimeError('DDS只读预检执行失败：'+r.stderr)
    data=[json.loads(line) for line in r.stdout.splitlines() if line.startswith('{')]
    return validate_dds_probe(data)

def motion_handoff(release=False):
    args=[str(ROOT/'.venv_sim/bin/python'),'-m','official_sonic.motion_handoff']
    if release:args.append('--operator-release')
    r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=35)
    if r.returncode:raise RuntimeError('运控接管失败：'+r.stderr.strip())
    return json.loads(r.stdout)

def preflight(config,run=None,progress=None):
    verify_health_hold()
    def mark(phase,note):
        if progress:progress.set(phase,note);progress.write(BASE/'startup-status.json')
    d=remote_action(config,'inspect');actions=startup_actions(d)
    mark('MODEL_RUNTIME_CHECK','核验v1.1三件套、容器和运行库；尚未启控')
    print('检查/准备SONIC运行环境（不启控）……',flush=True)
    d=remote_action(config,'prepare')
    mark('MOTION_MODE','查询运控与执行本次已授权接管；不重复释放')
    print('查询机载运控并按已确认的启动操作释放ai模式……',flush=True)
    handoff=motion_handoff(release=True)
    d['motion_handoff']=handoff
    if run is not None:(run/'motion-handoff.json').write_text(json.dumps(handoff,indent=2))
    print('释放完成后只读核验身体DDS控制权与状态……',flush=True)
    mark('DDS_CHECK','核验LowState新鲜度与无其他LowCmd；尚未启动SONIC')
    d['dds']=body_dds_check(config,run)
    if 'start_dex1' in actions:
        print('启动已验证的Dex1服务（包含串口探测）……',flush=True)
        mark('DEX1_SERVICE','准备已授权Dex1服务')
        d.update(remote_action(config,'start-dex1'))
    else:print('复用已有Dex1服务',flush=True)
    return d

def body_command(config,session):
    args=['./target/release/g1_deploy_onnx_ref','enP8p1s0','policy/sonic_v1_1/model_decoder.onnx','reference/example/',
          '--obs-config','policy/sonic_v1_1/observation_config.yaml','--encoder-file','policy/sonic_v1_1/model_encoder.onnx',
          '--planner-file','planner/target_vel/V2/planner_sonic.onnx','--input-type','zmq_manager','--output-type','zmq',
          '--zmq-host',config.streamer_ip,'--zmq-port','5556','--zmq-out-port','5557','--enable-csv-logs',
          '--logs-dir','/workspace/g1_deploy/official_sessions/'+session]
    body='cd /workspace/g1_deploy; source /opt/ros/humble/setup.bash; '
    body+='export LD_LIBRARY_PATH=/workspace/g1_deploy/thirdparty/unitree_sdk2/thirdparty/lib/aarch64:/opt/TensorRT/lib:/opt/onnxruntime/lib:/usr/local/lib:/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu/nvidia:$LD_LIBRARY_PATH; '
    body+='ulimit -c 0; exec '+shlex.join(args)
    remote='docker exec -it g1-deploy-dev bash -c '+shlex.quote(body)
    base=ssh_args(config);return base[:1]+['-tt']+base[1:]+[remote]

def pico_ready(path,process):
    if process.poll() is not None:return False
    path=Path(path)
    if not path.exists():return False
    try:d=json.loads(path.read_text())
    except (OSError,ValueError):return False
    return bool(d.get('reason')=='ready' and not d.get('fault_latched') and
                d.get('accepted_frames',0)>=20 and 0<=time.time()-path.stat().st_mtime<.5)

def wait_for_dex1_feedback(path,process,timeout=5.,clock=time.monotonic,pause=time.sleep):
    """Read bridge telemetry before starting the body; never publish or re-probe."""
    deadline=clock()+timeout;missing=['左夹爪','右夹爪'];path=Path(path)
    while True:
        if process.poll() is not None:
            raise RuntimeError('Dex1桥接已退出；未启动身体控制器，请查看dex1-mapping.log')
        now=clock()
        try:
            data=json.loads(path.read_text());state=data.get('state',{});missing=[]
            for side,label in [('left','左夹爪'),('right','右夹爪')]:
                item=state.get(side,{})
                values=[item.get(k) for k in ('q','dq','tau_est','at')]
                valid=all(type(x) in (int,float) and math.isfinite(x) for x in values)
                if not valid or not 0<=now-item['at']<.25:missing.append(label)
            if not missing and data.get('result') in ('WAITING','ACTIVE'):return data
        except (OSError,ValueError,TypeError,AttributeError):missing=['左夹爪','右夹爪']
        if now>=deadline:
            raise RuntimeError('、'.join(missing or ['双夹爪'])+'反馈未就绪；未启动身体控制器。请检查连接并恢复夹爪服务，不要重复按手柄。')
        pause(min(.05,max(0.,deadline-now)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true',help='Prepare runtime and check libraries without starting motor services');p.add_argument('--operator-start',action='store_true',help='Explicit operator confirmation already obtained')
    a=p.parse_args();config=ConfigStore().load()
    if a.check_only:
        wait_for_connection(config.robot_ip)
        print('启动前检查：只准备运行环境，不执行INIT、不进入IDLE、不解除热异常拦截。',flush=True)
        print(json.dumps(remote_action(config,'prepare'),ensure_ascii=False,indent=2))
        mode=motion_handoff();print(json.dumps(mode,ensure_ascii=False),flush=True)
        if mode['release_required']:
            print('机载ai运控正在运行；点击启动并确认现场条件后，将执行官方ReleaseMode，再核验LowCmd停止。只读检查不切换模式。',flush=True);return
        print(json.dumps(body_dds_check(config),ensure_ascii=False));return
    verify_health_hold()
    print('真机 SONIC + Dex1：INIT 将带力。需悬挂/可靠支撑、旁站与独立急停。',flush=True)
    print('左扳机→左夹爪，右扳机→右夹爪；按下闭合、激活后松开回到官方最大开度。首次操作请轻按。',flush=True)
    print('SONIC进入控制且两扳机松开后，两夹爪自动以0.5rad/s缓慢打开到官方最大开度。',flush=True)
    print('数采：保存三路相机、身体状态/命令、左右Dex1状态/命令。采集质量与训练适配须按实际episode验收。',flush=True)
    if not a.operator_start and input('确认现场条件并开始本轮，请输入 START：').strip()!='START':return
    base=ROOT/'official_sonic/real_sessions';base.mkdir(exist_ok=True)
    lock=(base/'session.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('本机已有真机遥操作会话')
    run=base/datetime.now().strftime('%Y%m%d-%H%M%S');run.mkdir()
    print('日志：'+str(run),flush=True);children=[];controller=None;master=None;stopping=False
    progress=StartupStatus();relay=ChildLogRelay(run,progress)
    env=os.environ.copy();env.update(PYTHONPATH=str(ROOT),PYTHONUNBUFFERED='1')
    def spawn(cmd,name,stdin=None):
        with (run/(name+'.log')).open('wb') as log:
            child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=stdin if stdin is not None else subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,close_fds=True)
        children.append((name,child));return child
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        progress.set('SSH_WAIT','等待机器人开机后SSH就绪；本次会话内等待，不需要反复点启动')
        progress.write(BASE/'startup-status.json');wait_for_connection(config.robot_ip)
        # Establish valid operator input before releasing onboard motion or starting motors.
        startup_actions(remote_action(config,'inspect'))
        print('先等待PICO真实输入；此阶段不释放机载运控、不启动身体控制器。',flush=True)
        progress.set('PICO_WAIT','等待PICO至少20帧有效追踪；尚未释放运控');progress.write(BASE/'startup-status.json')
        streamer=spawn([str(ROOT/'.venv_teleop/bin/python'),'-m','official_sonic.streamer','--enable-real-zmq',
                        '--dex1-input','--output',str(run/'pico.json')],'pico-streamer')
        end=time.monotonic()+120
        while time.monotonic()<end:
            relay.poll()
            if streamer.poll() is not None:raise RuntimeError('PICO输入启动未完成；身体未启动，详见pico-streamer日志中的数据包数量与原因')
            path=run/'pico.json'
            if path.exists():
                d=json.loads(path.read_text())
                if pico_ready(path,streamer):break
            time.sleep(.05)
        else:raise RuntimeError('PICO有效全身数据超时；未启动身体控制器')
        from official_sonic.console.ensure_camera import ensure
        progress.set('CAMERA_WAIT','核验三路真实图像；尚未启动身体');progress.write(BASE/'startup-status.json')
        (run/'camera-ready.json').write_text(json.dumps(ensure(config),indent=2))
        (run/'preflight.json').write_text(json.dumps(preflight(config,run,progress),indent=2))
        if not pico_ready(run/'pico.json',streamer):raise RuntimeError('准备期间PICO已断开或输入过期；未启动身体控制器')
        bridge=spawn([str(ROOT/'.venv_sim/bin/python'),'-m','official_sonic.dex1_bridge','--enable-real-dex1',
                      '--open-on-start',
                      '--manager','tcp://'+config.streamer_ip+':5556','--feedback','tcp://'+config.robot_ip+':5557',
                      '--output',str(run/'dex1.json')],'dex1-mapping')
        progress.set('DEX1_FEEDBACK_WAIT','等待左右夹爪真实反馈；尚未启动身体控制器');progress.write(BASE/'startup-status.json')
        feedback=wait_for_dex1_feedback(run/'dex1.json',bridge)
        (run/'dex1-ready.json').write_text(json.dumps({'state':feedback['state'],'motion_commands_sent_by_check':0},indent=2))
        print('左右Dex1真实反馈已就绪，开始加载身体控制器。',flush=True)
        master,slave=pty.openpty()
        progress.set('CONTROLLER_LOADING','加载v1.1并等待INIT；松开按键，不要重复启动');progress.write(BASE/'startup-status.json')
        controller=spawn(body_command(config,run.name),'official-controller',slave);os.close(slave)
        spawn([str(ROOT/'.venv_data_collection/bin/python'),'-m','official_sonic.session_observer',
               '--output',str(run/'zmq.json'),'--seconds','86400'],'zmq-observer')
        spawn(capture_command(config),'capture')
        print('正在加载控制器，尚未完成 INIT：请松开手柄所有按键，等待明确的 Init Done 再按 ABXY。终端 Ctrl+C 请求停止。',flush=True)
        shown=False;reported=set();last_progress=0.;last_heat_log=0.
        while True:
            relay.poll()
            now=time.monotonic()
            if now-last_progress>=.5:
                try:
                    observed=json.loads((run/'zmq.json').read_text());thermal=observed.get('thermal')
                    if thermal and observed.get('last_age_s',{}).get('g1_debug',999)<1:
                        progress.observe_thermal(thermal)
                        if thermal.get('alert'):
                            if now-last_heat_log>=5:print('热风险：'+progress.alert,flush=True);last_heat_log=now
                except (OSError,ValueError):pass
                progress.write(BASE/'startup-status.json');progress.write(run/'startup-status.json');last_progress=now
            for name,code in check_child_health(children,reported):
                print(f'{name} 已暂停（代码{code}）；请查看对应日志，身体控制仍运行。',flush=True)
                (run/'gripper-degraded.json').write_text(json.dumps({'component':name,'exit_code':code,'body_session_continues':True}))
            if not shown and 'Init Done' in (run/'official-controller.log').read_text(errors='replace'):
                print('Init Done：ABXY一次后松开→等3秒，进入PLANNER。默认运动模式IDLE，左摇杆此时不会行走；AB一次选SLOW_WALK（日志须确认Mode -> 1），松开后才轻推左摇杆，右摇杆控制朝向。AX用于切入/返回POSE，不是启用走路键。首次真机请逐步验收，不连续切换跑跳模式。',flush=True);shown=True
            time.sleep(.1)
    except NormalSessionEnd as e:print(str(e),flush=True)
    except KeyboardInterrupt:print('请求停止本次遥操作',flush=True)
    finally:
        progress.phase='STOPPING';progress.note='等待本次会话清理，不自动重启控制器';progress.write(BASE/'startup-status.json')
        if controller and controller.poll() is None:
            os.write(master,b'O')
            try:controller.wait(timeout=25)
            except subprocess.TimeoutExpired:print('警告：控制器未确认退出，立即使用现场急停并检查机器人。',flush=True)
        for name,child in reversed(children):
            if child is controller:continue
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        if master is not None:os.close(master)
        result={name:child.poll() for name,child in children}
        relay.poll()
        relay.flush()
        (run/'exit.json').write_text(json.dumps(result,indent=2))
        progress.phase='STOPPED';progress.note='会话已结束；不自动重新启控';progress.write(BASE/'startup-status.json');progress.write(run/'startup-status.json')
        print('会话日志：'+str(run),flush=True)
        print('官方 Dex1 状态服务保留运行；无命令约1秒后按官方逻辑进入 BRAKE。',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as e:print('未通过/已停止：'+str(e),file=sys.stderr,flush=True);raise SystemExit(2)
