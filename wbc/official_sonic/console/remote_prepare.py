"""Reviewed remote preparation. Default action never starts a controller or motor service."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

BASE=Path('/home/unitree/GR00T-WholeBodyControl/gear_sonic_deploy')
DEX=BASE/'dex1_official_ced3216'
NAME='g1-deploy-dev'
LABEL='sonic.workstation.prepared'
IMAGE='g1-deploy-dev:latest'
MODEL_HASHES={
    'model_encoder.onnx':'fb97de22819b2057b41459802128d91723d91a25f0ad73e7bfc41a9cf8365bae',
    'model_decoder.onnx':'34bae8570d4a4421a5391a5c2befd745d4a02d182ec539e5f9da44c091c67509',
    'observation_config.yaml':'4a67713b310932e50aca81f19188c8d76013148e98b15c8b5bbea995f12e59f0',
}

def verify_model():
    model=BASE/'policy/sonic_v1_1';actual={}
    for name,expected in MODEL_HASHES.items():
        path=model/name
        if not path.is_file():raise RuntimeError('SONIC v1.1 文件缺失：'+str(path)+'；拒绝回退旧版')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=expected:raise RuntimeError('SONIC v1.1 哈希不匹配：'+str(path)+'；拒绝启动或回退旧版')
        actual[name]=digest
    return {'version':'SONIC v1.1','directory':str(model),'hashes':actual}

def run(args,**kw):
    return subprocess.run(args,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,**kw).stdout.strip()

def inspect():
    controllers=[];dex=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            args=(p/'cmdline').read_bytes().split(b'\0');exe=Path(args[0].decode()).name
            if exe in ('g1_deploy_onnx_ref','g1_deploy_real_trial'):controllers.append(int(p.name))
            if exe=='dex1_1_gripper_server':dex.append(int(p.name))
        except (OSError,UnicodeError):pass
    existing=subprocess.run(['docker','inspect','--type','container',NAME],text=True,capture_output=True)
    container=json.loads(existing.stdout)[0] if existing.returncode==0 else None
    return {'controllers':controllers,'dex1_pids':dex,
        'autostart':run(['systemctl','show','unitree_sonic.service','-p','ActiveState','--value']),
        'container_running':bool(container and container['State']['Running']),
        'container_exists':container is not None}

def prepare():
    model=verify_model()
    d=inspect()
    if d['controllers'] or d['autostart'] not in ('inactive','failed'):raise RuntimeError('已有控制器或自动启动器运行，拒绝准备第二条控制链')
    if not d['container_exists']:
        image=json.loads(run(['docker','image','inspect',IMAGE]))[0]['Id']
        args=['docker','create','--name',NAME,'--label',LABEL+'=1','--network','host','--ipc','host',
              '--runtime','nvidia','-e','NVIDIA_VISIBLE_DEVICES=all','-e','NVIDIA_DRIVER_CAPABILITIES=all',
              '-e','RMW_IMPLEMENTATION=rmw_fastrtps_cpp','-e','ROS_DOMAIN_ID=0',
              '--entrypoint','/bin/sleep','-w','/workspace/g1_deploy',
              '--mount',f'type=bind,src={BASE},dst=/workspace/g1_deploy',
              '--mount','type=bind,src=/home/unitree/GR00T-WholeBodyControl/gear_sonic,dst=/workspace/gear_sonic,readonly',
              '--mount','type=bind,src=/home/unitree/TensorRT,dst=/opt/TensorRT,readonly',
              '--mount','type=bind,src=/usr/local/cuda-12.6,dst=/usr/local/cuda,readonly',image,'infinity']
        run(args)
    config=json.loads(run(['docker','inspect','--type','container',NAME]))[0]
    mounts={m['Destination']:m['Source'] for m in config['Mounts']}
    if mounts.get('/workspace/g1_deploy')!=str(BASE):raise RuntimeError('Existing container workspace mismatch')
    if not config['State']['Running']:
        if config['Config'].get('Labels',{}).get(LABEL)!='1':raise RuntimeError('Existing stopped container was not prepared by workstation; inspect before starting')
        run(['docker','start',NAME])
    # Shell and library checks only; never execute the controller to test dependencies.
    check='source /opt/ros/humble/setup.bash; export LD_LIBRARY_PATH=/workspace/g1_deploy/thirdparty/unitree_sdk2/thirdparty/lib/aarch64:/opt/TensorRT/lib:/opt/onnxruntime/lib:/usr/local/lib:/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu/nvidia:$LD_LIBRARY_PATH; ldd /workspace/g1_deploy/target/release/g1_deploy_onnx_ref'
    libs=run(['docker','exec',NAME,'bash','-c',check])
    if 'not found' in libs:raise RuntimeError('控制器运行库缺失: '+libs)
    version=run(['env','LD_LIBRARY_PATH='+dex1_library_path(),str(DEX/'bin/dex1_1_gripper_server'),'--version'])
    return dict(inspect(),controller_libraries='PASS',dex1_binary=version,sonic_model=model)

def dex1_library_path():
    # Exact path and priority captured from the successful 20261027-103240 session.
    return ':'.join(map(str,[DEX/'user-deps/usr/lib/aarch64-linux-gnu',DEX/'lib',BASE/'thirdparty/unitree_sdk2/thirdparty/lib/aarch64']))

def restore_dex1():
    d=inspect()
    if d['controllers'] or d['autostart'] not in ('inactive','failed'):raise RuntimeError('身体控制尚在运行，拒绝重启夹爪服务')
    if len(d['dex1_pids'])>1:raise RuntimeError('夹爪服务多实例，拒绝自动处理')
    for pid in d['dex1_pids']:
        exe=run(['sudo','-n','readlink','-f',f'/proc/{pid}/exe'])
        if exe!=str(DEX/'bin/dex1_1_gripper_server'):raise RuntimeError('夹爪进程路径与上午基线不一致')
        run(['sudo','-n','kill','-TERM',str(pid)])
    deadline=time.monotonic()+5
    while inspect()['dex1_pids'] and time.monotonic()<deadline:time.sleep(.1)
    if inspect()['dex1_pids']:raise RuntimeError('旧夹爪服务未正常退出，未强杀')
    return start_dex1()

def start_dex1():
    d=inspect()
    if d['controllers'] or d['autostart'] not in ('inactive','failed'):raise RuntimeError('控制器已运行，拒绝隐式启动夹爪')
    if len(d['dex1_pids'])==1:return d
    if d['dex1_pids']:raise RuntimeError('多个Dex1进程，拒绝重复启动')
    log=Path('/home/unitree/.local/state/sonic-workstation');log.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['LD_LIBRARY_PATH']=dex1_library_path()
    # Only reached after the desktop operator-start confirmation; startup probes FOC.
    with (log/'dex1.log').open('ab') as f:
        child=subprocess.Popen(['sudo','-n','--','env','LD_LIBRARY_PATH='+env['LD_LIBRARY_PATH'],str(DEX/'bin/dex1_1_gripper_server'),'--network','enP8p1s0'],
            cwd=DEX,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    time.sleep(3)
    if child.poll() is not None:raise RuntimeError('Dex1启动失败: '+(log/'dex1.log').read_text(errors='replace')[-3000:])
    d=inspect()
    if len(d['dex1_pids'])!=1:raise RuntimeError('Dex1进程数异常')
    return d

if __name__=='__main__':
    try:
        action=sys.argv[1];result={'inspect':inspect,'verify-model':verify_model,'prepare':prepare,'start-dex1':start_dex1,'restore-dex1':restore_dex1}[action]()
        print(json.dumps(result))
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(2)
