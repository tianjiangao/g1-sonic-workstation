"""User-only supervisor. All DDS and simulation children share a private netns."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'sim_teleop'
STATE=BASE/'state.json'
STOP=False

def halt(*_):
    global STOP
    STOP=True

def write_json(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)

def tick(pid):
    # comm may contain spaces; split after last closing parenthesis.
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]

def alive(state):
    try:return tick(state['pid'])==state['start_tick'] and Path(f"/proc/{state['pid']}/stat").read_text().rsplit(')',1)[1].split()[0]!='Z'
    except (OSError,KeyError):return False

def child(command,log,env=None,session=False,stdin=None):
    out=open(log,'ab',buffering=0)
    try:
        return subprocess.Popen(command,cwd=ROOT,env=env,stdin=stdin or subprocess.DEVNULL,
                                stdout=out,stderr=subprocess.STDOUT,close_fds=True,start_new_session=session)
    finally:out.close()

def wait_for_file(path,process,timeout=10):
    end=time.monotonic()+timeout
    while time.monotonic()<end and not STOP:
        if process.poll() is not None:raise RuntimeError(f'Child exited {process.returncode}: {path}')
        if path.exists():return
        time.sleep(.05)
    raise RuntimeError(f'Timed out: {path}')

def environment():
    env=os.environ.copy()
    env.update(PYTHONPATH=str(ROOT),PYTHONUNBUFFERED='1',ROS_DOMAIN_ID='117',
               ROS_LOCALHOST_ONLY='1',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',OMP_NUM_THREADS='2')
    # Do not inherit external DDS transport/profile configuration.
    for key in ('CYCLONEDDS_URI','FASTRTPS_DEFAULT_PROFILES_FILE','FASTDDS_DEFAULT_PROFILES_FILE'):
        env.pop(key,None)
    return env

def inside(args):
    from sim_teleop.safety import assert_isolated
    subprocess.run(['ip','link','set','lo','up'],check=True)
    evidence=Path(args.run)
    write_json(evidence/'isolation.json',assert_isolated())
    processes=[]; master=None
    signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
    def launch(command,name,stdin=None,env=None):
        assert_isolated()
        p=child(command,evidence/(name+'.log'),stdin=stdin,env=env);processes.append(p)
        write_json(evidence/'children.json',{'pids':[p.pid for p in processes]})
        return p
    try:
        proxy=launch([sys.executable,'-m','sim_teleop.sdk_relay',args.socket,'--inside'],'sdk-inside')
        time.sleep(.3)
        if args.mode=='probe':
            probe=launch([str(ROOT/'.venv_teleop/bin/python'),'-m','sim_teleop.atomic_streamer','--probe','--output',str(evidence/'pico.json')],'pico-probe')
            return probe.wait(timeout=25)
        if args.mode=='teleop':
            probe=launch([str(ROOT/'.venv_teleop/bin/python'),'-m','sim_teleop.atomic_streamer','--probe','--output',str(evidence/'pico.json')],'pico-probe')
            result=probe.wait(timeout=25);processes.remove(probe)
            if result:raise RuntimeError('PICO 24-joint freshness preflight failed; controller NOT launched')
        sim=[str(ROOT/'.venv_sim/bin/python'),'-m','sim_teleop.sim_loop','--run',str(evidence)]
        if args.headless:sim+=['--headless']
        sim_env=os.environ.copy()
        sim_env.update(LIBGL_ALWAYS_SOFTWARE='1',__GLX_VENDOR_LIBRARY_NAME='mesa',MESA_SHADER_CACHE_DIR=str(evidence/'mesa-cache'))
        launch(sim,'mujoco',env=sim_env)
        time.sleep(4)
        launch([str(ROOT/'.venv_sim/bin/python'),'-m','sim_teleop.dds_monitor','--output',str(evidence/'dds.json')],'dds-monitor')
        launch([str(ROOT/'.venv_sim/bin/python'),'-m','sim_teleop.telemetry','--output',str(evidence/'telemetry.json')],'telemetry')
        if args.mode=='teleop':
            launch([str(ROOT/'.venv_teleop/bin/python'),'-m','sim_teleop.atomic_streamer','--output',str(evidence/'pico-live.json')],'pico-bridge')
        master,slave=pty.openpty()
        deploy=ROOT/'gear_sonic_deploy'
        command=[str(BASE/'bin/g1_deploy_sim'),'lo',str(deploy/'policy/sonic_v1_1/model_decoder.onnx'),
                 str(deploy/'reference/example'),'--encoder-file',str(deploy/'policy/sonic_v1_1/model_encoder.onnx'),
                 '--obs-config',str(deploy/'policy/sonic_v1_1/observation_config.yaml'),
                 '--planner-file',str(deploy/'planner/target_vel/V2/planner_sonic.onnx'),
                 '--input-type','zmq_manager' if args.mode=='teleop' else 'keyboard','--output-type','zmq',
                 '--zmq-host','127.0.0.1','--disable-crc-check']
        # Cached v1.1 engines belong to the v1.1 ONNX/config triplet; never mix release variants.
        ctrl_env=os.environ.copy()
        vendor=deploy/'thirdparty/unitree_sdk2/thirdparty/lib/x86_64'
        ctrl_env['LD_LIBRARY_PATH']=str(vendor)+':'+ctrl_env.get('LD_LIBRARY_PATH','')
        ctrl=launch(command,'sonic',stdin=slave,env=ctrl_env);os.close(slave)
        start=time.monotonic(); activated=False
        while not STOP:
            assert_isolated()
            if (evidence/'operator-stop.json').exists():
                print('OPERATOR_STOP: received explicit stop command',flush=True)
                break
            for p in processes:
                if p.poll() is not None:
                    # Allow the independent observer to consume the stop packet
                    # sent immediately before the official manager exits.
                    end=time.monotonic()+.5
                    while time.monotonic()<end and not (evidence/'operator-stop.json').exists():time.sleep(.01)
                    if (evidence/'operator-stop.json').exists():return 0
                    raise RuntimeError(f'Child {p.pid} exited {p.returncode}; stopping whole simulation')
            if args.mode=='offline' and not activated and 'Init Done' in (evidence/'sonic.log').read_text(errors='replace'):
                os.write(master,b']');activated=True
            if args.seconds and time.monotonic()-start>args.seconds:break
            write_json(evidence/'heartbeat.json',{'monotonic':time.monotonic(),'pid':os.getpid(),'mode':args.mode})
            time.sleep(.1)
        return 0
    finally:
        for p in reversed(processes):
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        if master is not None:os.close(master)

def host(args):
    BASE.mkdir(exist_ok=True)
    os.umask(0o077)
    with (BASE/'instance.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('An instance is already running')
        run=BASE/'logs'/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000));run.mkdir(parents=True,mode=0o700)
        runtime=Path(tempfile.mkdtemp(prefix='sonic-sim-',dir=os.environ.get('XDG_RUNTIME_DIR','/tmp')))
        os.chmod(runtime,0o700);sock=runtime/'sdk.sock'
        signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
        env=environment();env['SONIC_HOST_NETNS']=os.readlink('/proc/self/ns/net')
        processes=[]
        state={'pid':os.getpid(),'start_tick':tick(os.getpid()),'run':str(run),'mode':args.mode,'status':'starting'}
        write_json(STATE,state)
        try:
            if args.mode!='offline':
                with socket.create_connection(('127.0.0.1',60061),timeout=1):pass
            relay=child([sys.executable,'-m','sim_teleop.sdk_relay',str(sock)],run/'sdk-host.log',env,True)
            processes.append(relay);wait_for_file(sock,relay)
            cmd=['unshare','--user','--map-root-user','--net',sys.executable,'-m','sim_teleop.runner','inside',
                 '--mode',args.mode,'--run',str(run),'--socket',str(sock),'--seconds',str(args.seconds)]
            if args.headless:cmd+=['--headless']
            ns=child(cmd,run/'supervisor.log',env,True);processes.append(ns)
            state.update(namespace_pid=ns.pid,relay_pid=relay.pid,status='running');write_json(STATE,state)
            print('RUN',run,flush=True)
            while not STOP:
                if relay.poll() is not None:raise RuntimeError('SDK relay exited')
                if ns.poll() is not None:
                    state['exit_code']=ns.returncode
                    return ns.returncode
                time.sleep(.1)
            return 0
        finally:
            for p in reversed(processes):
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            for p in processes:
                try:p.wait(timeout=6)
                except subprocess.TimeoutExpired:pass
                # Kill leftover descendants even when their leader has already exited.
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            if sock.exists():sock.unlink()
            runtime.rmdir()
            state['status']='stopped';write_json(STATE,state)

def check_running(state):
    run=Path(state['run'])
    baseline=json.loads((run/'isolation.json').read_text())
    expected=baseline['network_namespace']
    pids=[state['namespace_pid']]+json.loads((run/'children.json').read_text())['pids']
    results={}
    for pid in pids:
        net=os.readlink(f'/proc/{pid}/ns/net')
        devices=Path(f'/proc/{pid}/net/dev').read_text().splitlines()[2:]
        interfaces=[line.split(':')[0].strip() for line in devices]
        routes=Path(f'/proc/{pid}/net/route').read_text().splitlines()[1:]
        if net!=expected or net==baseline['host_namespace'] or set(interfaces)!={'lo'} or routes:
            raise RuntimeError(f'Live isolation violation in child {pid}')
        results[pid]={'netns':net,'interfaces':interfaces,'ipv4_route_count':len(routes)}
    heartbeat=json.loads((run/'heartbeat.json').read_text()) if (run/'heartbeat.json').exists() else None
    return {'children':results,'heartbeat_age_s':time.monotonic()-heartbeat['monotonic'] if heartbeat else None}


def main():
    os.chdir(ROOT)
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','inside','stop','status','check'])
    p.add_argument('--mode',choices=['teleop','offline','probe'],default='teleop')
    p.add_argument('--seconds',type=float,default=0);p.add_argument('--headless',action='store_true')
    p.add_argument('--run');p.add_argument('--socket');a=p.parse_args()
    if a.action=='inside':return inside(a)
    if a.action=='start':return host(a)
    if a.action=='check':
        if STATE.exists():
            state=json.loads(STATE.read_text())
            if alive(state):print(json.dumps({'live_safety':check_running(state)},indent=2),flush=True)
        env=environment();env['SONIC_HOST_NETNS']=os.readlink('/proc/self/ns/net')
        return subprocess.call(['unshare','--user','--map-root-user','--net','bash','-c',
                                'ip link set lo up && exec python3 -m sim_teleop.safety'],env=env,cwd=ROOT,close_fds=True)
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    if a.action=='stop':
        if state and alive(state):
            os.kill(state['pid'],signal.SIGTERM)
            end=time.monotonic()+12
            while alive(state) and time.monotonic()<end:time.sleep(.1)
            if alive(state):raise RuntimeError('Owned supervisor did not exit; inspect logs')
            print('Owned simulation stopped')
        else:print('No owned running instance')
        return 0
    state['supervisor_alive']=bool(state and alive(state))
    if state.get('run'):
        for name in ('isolation','heartbeat','dds','pico','pico-live','telemetry'):
            path=Path(state['run'])/(name+'.json')
            if path.exists():state[name]=json.loads(path.read_text())
    if state['supervisor_alive']:
        state['live_safety']=check_running(state)
    else:
        state['historical_metrics_only']=True
    print(json.dumps(state,indent=2));return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:print('BLOCKED/FAIL:',str(e),file=sys.stderr,flush=True);raise SystemExit(2)
