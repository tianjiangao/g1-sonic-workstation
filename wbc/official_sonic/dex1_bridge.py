"""PICO→official Unitree Dex1 adapter. Never publishes rt/lowcmd."""
import argparse
import json
import math
from pathlib import Path
import signal
import threading
import time
import zmq
from official_sonic.dex1_mapping import InputGate,TriggerTargets,load_routes
from official_sonic.unitree_dex1 import OfficialLoop
from sim_teleop.telemetry import decode

def run(a):
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize,ChannelPublisher,ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorCmds_,MotorStates_
    if a.simulation:
        from sim_teleop.safety import assert_isolated
        assert_isolated();network='lo'
    else:
        if not a.enable_real_dex1:raise ValueError('Real Dex1 requires --enable-real-dex1')
        network='enp4s0'
    from official_sonic.dex1_transport import initialize
    transport=initialize(network)
    routes=load_routes(a.route_profile) if a.route_profile or not a.simulation else {'left':'left','right':'right'}
    gate=InputGate();ctx=zmq.Context();poll=zmq.Poller();sockets=[]
    for endpoint,topic in [(a.input,b'dex1_trigger'),(a.manager,b'manager_state'),(a.feedback,b'g1_debug')]:
        s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,topic);s.setsockopt(zmq.RCVHWM,2);s.setsockopt(zmq.CONFLATE,1)
        s.connect(endpoint);poll.register(s,zmq.POLLIN);sockets.append(s)
    state={};published={'left':0,'right':0};last_cmd={};mutex=threading.Lock()
    policy_at=None;enabled=False;fault=None;ever_active=False;activation={'left':False,'right':False}
    released_since=None;release_ready=False;engine=None;subscribers=[];publishers={};openings=None
    limiter=None;limited_at=None;fault_sample=None;targets=None
    def receive(side,msg):
        nonlocal fault,fault_sample
        if not msg.states:return
        q=float(msg.states[0].q);dq=float(msg.states[0].dq);tau=float(msg.states[0].tau_est)
        with mutex:
            from official_sonic.dex1_mapping import validate_feedback
            try:validate_feedback(q,dq,tau)
            except ValueError:
                if fault is None:
                    fault='nonfinite Dex1 feedback: '+side
                    fault_sample={'side':side,'q':q,'dq':dq,'tau_est':tau,'at':time.monotonic()}
            state[side]={'q':q,'dq':dq,'tau_est':tau,'at':time.monotonic()}
            if engine:engine.set_state(side,q)
    def allowed(now):
        return bool(enabled and fault is None and gate.allowed(now) and policy_at is not None and
                    0<=now-policy_at<.25 and all(k in state and 0<=now-state[k]['at']<.25 for k in ('left','right')))
    def publish(side,msg):
        nonlocal fault
        with mutex:
            if not allowed(time.monotonic()):return False
            m=msg.cmds[0];values=[float(v) for v in (m.q,m.dq,m.tau,m.kp,m.kd)]
            if not all(math.isfinite(v) for v in values) or not -.01<=m.q<=5.41 or not 0<=m.kp<=5 or not 0<=m.kd<=.05:
                fault='invalid official Dex1 output';return False
            # Match the official C++ Dex1 publisher's enabled mode field.
            m.mode=1
            # Require a matched subscriber; bare SDK Write can succeed unpaired.
            if publishers[side].Write(msg,timeout=.01) is False:
                fault='Dex1 DDS write failed: '+side;return False
            published[side]+=1;last_cmd[side]=dict(zip(['q','dq','tau','kp','kd'],values));return True
    for side in ('left','right'):
        pub=ChannelPublisher('rt/dex1/'+routes[side]+'/cmd',MotorCmds_);pub.Init();publishers[side]=pub
        sub=ChannelSubscriber('rt/dex1/'+routes[side]+'/state',MotorStates_);sub.Init(lambda m,k=side:receive(k,m),10);subscribers.append(sub)
    # Do not run the upstream filter against zero/unavailable startup state:
    # its history would otherwise cause a jump when output is first enabled.
    engine=OfficialLoop(publish);out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();saved=start;result={'result':'WAITING','published':published};trace=out.with_suffix('.jsonl').open('a',buffering=1)
    print('DEX1: official Unitree control loop; wait for active SONIC + fresh PICO + released triggers',flush=True)
    try:
        while not a.seconds or time.monotonic()-start<a.seconds:
            for sock,_ in poll.poll(5):
                data=sock.recv();now=time.monotonic()
                if data.startswith(b'dex1_trigger'):
                    packet=json.loads(data[len(b'dex1_trigger'):]);gate.update_trigger(packet,now)
                elif data.startswith(b'manager_state'):
                    packet=decode(data,b'manager_state');gate.update_manager(int(packet['stream_mode'][0]),now)
                elif data.startswith(b'g1_debug'):policy_at=now
            now=time.monotonic()
            with mutex:
                if fault:raise RuntimeError(fault)
                base=gate.allowed(now) and policy_at is not None and now-policy_at<.25 and all(k in state and now-state[k]['at']<.25 for k in ('left','right'))
                if ever_active and not base:raise RuntimeError('Dex1 input/state/controller timeout or mode stopped; restart required')
                if base:
                    left,right=gate.packet['left'],gate.packet['right']
                    if not release_ready:
                        if max(left,right)<=.05:
                            if released_since is None:released_since=now
                            release_ready=now-released_since>=.25
                        else:released_since=None
                    if release_ready:
                        if openings is None:
                            openings=tuple(min(5.4,max(0.,state[k]['q'])) for k in ('left','right'))
                            targets=TriggerTargets(openings,return_to_start=a.return_to_start_opening,auto_open=a.open_on_start)
                            activation=targets.activated
                            from official_sonic.dex1_mapping import TrialLimiter
                            limiter=TrialLimiter(openings);limited_at=now
                        values=targets.advance(left,right,tuple(state[k]['q'] for k in ('left','right')),dt=now-limited_at)
                        if a.commissioning_limits:values=limiter.advance(values,now-limited_at)
                        limited_at=now
                        engine.set_input(*values,True);enabled=True;ever_active=True
                        if engine.thread.ident is None:
                            for k in ('left','right'):engine.set_state(k,state[k]['q'])
                            engine.start()
                    else:enabled=False;engine.set_input(6.,6.,False)
                else:enabled=False;engine.set_input(6.,6.,False)
                if now-saved>=.05:
                    result={'result':'ACTIVE' if enabled else 'WAITING','elapsed_s':now-start,'host_epoch':time.time(),
                        'published':dict(published),'state':{k:dict(v) for k,v in state.items()},'last_command':dict(last_cmd),
                        'trigger':gate.packet,'mode':gate.mode,'release_ready':release_ready,'hand_activated':dict(activation),
                        'dds_transport':transport,'physical_to_wire':routes,'captured_opening_q':openings,'commissioning_limits':{'enabled':a.commissioning_limits,'target_speed_rad_s':.5,'closed_floor_rad':.15},
                        'release_opening_policy':('commissioning_start_limit' if a.commissioning_limits else 'return_to_start' if a.return_to_start_opening else 'official_full_open_after_activation'),
                        'release_opening_target_q':list(openings if a.commissioning_limits else targets.limits) if targets else None,
                        'automatic_opening':{'enabled':a.open_on_start,'speed_rad_s':.5,'pending':list(targets.opening_pending) if targets else None},
                        'real_motion_verified':False,'upstream_loop':'Unitree Dex1_1_Gripper_Controller.control_thread'}
                    trace.write(json.dumps(result)+'\n');tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2));tmp.replace(out);saved=now
    except BaseException as e:
        result.update(result='STOPPED',reason=str(e),fault_sample=fault_sample,published=dict(published));out.write_text(json.dumps(result,indent=2));raise
    finally:
        enabled=False;engine.stop();trace.close()
        for s in sockets:s.close()
        ctx.term()

def main():
    p=argparse.ArgumentParser();p.add_argument('--enable-real-dex1',action='store_true');p.add_argument('--simulation',action='store_true')
    p.add_argument('--input',default='tcp://127.0.0.1:5558');p.add_argument('--manager',default='tcp://192.168.123.99:5556')
    p.add_argument('--route-profile',help='physical-to-wire profile; simulation defaults to identity')
    p.add_argument('--commissioning-limits',action='store_true',help='optional 0.5rad/s target slew and 0.15rad closing margin; default uses upstream full range')
    p.add_argument('--return-to-start-opening',action='store_true',help='manual rollback: release returns to captured session opening instead of official full opening')
    p.add_argument('--open-on-start',action='store_true',help='after fresh active SONIC and released triggers, automatically ramp both openings at 0.5rad/s; never rearms after a fault')
    p.add_argument('--feedback',default='tcp://192.168.123.164:5557');p.add_argument('--output',required=True);p.add_argument('--seconds',type=float,default=0)
    a=p.parse_args()
    def stop(*_):raise KeyboardInterrupt('operator stopped')
    signal.signal(signal.SIGTERM,stop)
    try:run(a)
    except KeyboardInterrupt:print('Dex1 bridge stopped by operator',flush=True)

if __name__=='__main__':main()
