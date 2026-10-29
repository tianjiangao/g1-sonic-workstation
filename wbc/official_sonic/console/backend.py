"""Workstation orchestration only. No DDS publishers, SSH, or robot RPC."""
from dataclasses import asdict, dataclass
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'official_sonic/console'
BLOCKERS=('Dex1 控制与采集模型未接通', '头部 D435i 尚未枚举（双腕 D405 映射与15Hz图像传输已验证）',
          '官方 PICO 入口兼容性与真机端到端未验收')

@dataclass
class Config:
    robot_ip:str='192.168.123.164'
    camera_ip:str='192.168.123.164'
    streamer_ip:str='192.168.123.99'
    task:str='抓取并放置杯子'
    dataset:str='g1_demo'
    output:str=str(ROOT/'outputs/real_sessions')
    frequency:int=15
    def validate(self):
        for x in (self.robot_ip,self.camera_ip,self.streamer_ip):
            ipaddress.IPv4Address(x)
        if not isinstance(self.task,str) or not self.task.strip() or len(self.task)>200:
            raise ValueError('任务描述须为 1–200 个字符')
        if any(c in self.task for c in "'\"\n\r\x00`$;&|<>()\\"):
            raise ValueError('官方 tmux 启动器会拼接 shell 文本，任务描述暂不允许引号、换行或 shell 符号')
        if not isinstance(self.dataset,str) or not re.fullmatch(r'[\w-]{1,64}',self.dataset):
            raise ValueError('数据集名称只允许文字、数字、下划线和连字符，最多64字')
        if type(self.frequency) is not int or not 1<=self.frequency<=100:
            raise ValueError('采集频率须为 1–100 的整数')
        if not isinstance(self.output,str) or not Path(self.output).is_absolute() or '\x00' in self.output:
            raise ValueError('保存目录须为绝对路径')
        return self

class ConfigStore:
    def __init__(self,path=BASE/'settings.json'):self.path=Path(path)
    def load(self):
        if not self.path.exists():return Config()
        try:return Config(**json.loads(self.path.read_text())).validate()
        except (TypeError,ValueError) as e:raise ValueError('设置文件无效：'+str(e)) from e
    def save(self,config):
        config.validate();self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            backup=self.path.with_name('settings.'+str(time.time_ns())+'.bak')
            shutil.copy2(self.path,backup)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(config),ensure_ascii=False,indent=2))
        tmp.chmod(0o600);tmp.replace(self.path)

def real_command(config):
    config.validate()
    raise RuntimeError('真机入口尚未验收，当前版本不可启控：'+'；'.join(BLOCKERS))

def preview(config):
    config.validate()
    return {'execution':'PREVIEW_ONLY; no process started',
            'architecture':'既有SONIC控制 / 工作站PICO与被动数采',
            'data_exporter':capture_command(config),
            'format':'原始事件/JPEG → 离线官方LeRobot导出；G1_29+Dex1',
            'acceptance':'真实episode与同步质量按实际保存结果检查'}

def local_status():
    rows=[]
    for label,rel in [('遥操作环境','.venv_teleop/bin/python'),('仿真环境','.venv_sim/bin/python'),
                      ('官方采集环境','.venv_data_collection/bin/python')]:
        ok=(ROOT/rel).exists();rows.append((label,'已安装' if ok else '缺失',rel))
    assets=[ROOT/'gear_sonic_deploy/policy/sonic_v1_1'/n for n in
            ['model_encoder.onnx','model_decoder.onnx','observation_config.yaml']]
    assets.append(ROOT/'gear_sonic_deploy/planner/target_vel/V2/planner_sonic.onnx')
    ok=all(p.exists() and p.stat().st_size>1024 for p in assets)
    rows.append(('官方模型','本机文件齐全' if ok else '缺失','真机入口已选择 SONIC v1.1 三件套；启动前核验机载哈希；热安全暂缓仍独立生效'))
    hold=ROOT/'official_sonic/health_hold.json'
    if hold.exists():
        try:
            health=json.loads(hold.read_text())
            if health.get('blocked'):rows.append(('热安全','暂缓真机启动',health.get('reason','健康异常待排查')))
        except (OSError,ValueError,AttributeError):rows.append(('热安全','健康记录不可用','拒绝新真机会话，需检查记录'))
    rows.append(('隔离仿真','入口就绪' if shutil.which('unshare') and (ROOT/'sim_teleop/bin/g1_deploy_sim').exists() else '缺失',
                 '复用已验收入口；每次启动重新检查网络隔离'))
    try:
        with socket.create_connection(('127.0.0.1',60061),timeout=.3):pass
        sdk='端口可达'
    except OSError:sdk='未连接'
    rows.append(('PICO PC Service',sdk,'仅检查本机 SDK 端口；全身追踪需点击「检查 PICO 数据」'))
    try:carrier=Path('/sys/class/net/enp4s0/carrier').read_text().strip()=='1'
    except OSError:carrier=False
    rows.append(('机器人有线链路','有载波' if carrier else '无网线','未登录、未探测控制端口；有载波也不等于机器人已就绪'))
    rows.append(('全身遥操与数采','可启动检查','复用既有SONIC与Dex1；真实episode质量仍需验收'))
    return rows

CAPTURE_HOME=Path('/opt/g1/workspace')
CAPTURE_COMMAND=BASE/'capture-command.json'

def capture_command(config):
    config.validate()
    return [str(CAPTURE_HOME/'capture/start.sh'),'--task',config.task,
            '--output-root',str(Path(config.output)/config.dataset),'--fps',str(min(config.frequency,30)),
            '--robot-host',config.robot_ip,'--camera-host',config.camera_ip,'--pico-host',config.streamer_ip,
            '--command-file',str(CAPTURE_COMMAND)]

def recording_request(action):
    if action not in ('start','toggle','stop','finish_batch'):raise ValueError('invalid capture action')
    tmp=CAPTURE_COMMAND.with_suffix('.tmp')
    tmp.write_text(json.dumps({'id':time.time_ns(),'action':action}));tmp.replace(CAPTURE_COMMAND)


def commands():
    return {'voice':[str(ROOT/'.venv_sim/bin/python'),str(CAPTURE_HOME/'capture/speech.py'),'--text','机器人数采语音测试，当前没有开始录制。'],'export':['python3','-m','official_sonic.console.export_capture'],'capture':capture_command(ConfigStore().load()),'prepare':['python3','-m','official_sonic.run_real_teleop','--check-only'],'real':['python3','-m','official_sonic.run_real_teleop','--operator-start'],
            'camera':['python3','-m','official_sonic.console.ensure_camera'],
            'inventory':['python3','-m','official_sonic.console.remote_inventory'],
            'service':[str(ROOT/'.venv_teleop/bin/python'),'-c',
                       'from gear_sonic.utils.teleop.xrt_runtime import ensure_pc_service; ensure_pc_service()'],
            'check':[str(ROOT/'.venv_data_collection/bin/python'),'-m','official_sonic.console.selfcheck',
                     '--output-root',str(BASE/'selftests')],
            'pico':['bash',str(ROOT/'start_sim_teleop.sh'),'--mode','probe'],
            'sim':['bash',str(ROOT/'start_sim_teleop.sh')],
            'offline':['bash',str(ROOT/'start_sim_teleop.sh'),'--mode','offline','--headless','--seconds','15']}

class JobManager:
    def __init__(self,log_root,allowed):
        self.root=Path(log_root);self.allowed=allowed;self.process=None;self.log=None;self.name=None;self.started=None;self.start_tick=None
    def running(self):return self.process is not None and self.process.poll() is None
    def start(self,name):
        if name not in self.allowed:raise ValueError('不允许的作业')
        if self.running():raise RuntimeError('本控制台已有作业运行，请先停止或等待完成')
        run=self.root/datetime.now().strftime('%Y%m%d-%H%M%S-%f');run.mkdir(parents=True,mode=0o700)
        self.log=run/'console.log';env=os.environ.copy();env['PYTHONPATH']=str(ROOT);env['PYTHONUNBUFFERED']='1'
        with self.log.open('wb') as out:
            p=subprocess.Popen(self.allowed[name],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                               stdout=out,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        self.process=p;self.name=name;self.started=datetime.now().isoformat(timespec='seconds')
        self.start_tick=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        (run/'job.json').write_text(json.dumps({'name':name,'pid':p.pid,'start_tick':self.start_tick,
                       'started':self.started,'argv':self.allowed[name]},ensure_ascii=False,indent=2))
        return p
    def stop(self):
        if not self.running():return
        p=self.process
        tick=Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        if tick!=self.start_tick:raise RuntimeError('进程身份已变化，拒绝停止')
        # Signal only the process created by this instance. The existing sim
        # supervisor owns namespace/relay cleanup, never an external session.
        p.terminate()
        try:p.wait(timeout=50 if self.name=='real' else 18)
        except subprocess.TimeoutExpired:raise RuntimeError('作业未按时退出，请查看日志；未强杀其他程序')
    def snapshot(self):
        return {'name':self.name,'pid':self.process.pid if self.process else None,
                'started':self.started,'running':self.running(),
                'returncode':self.process.poll() if self.process else None,
                'log':str(self.log) if self.log else None}
