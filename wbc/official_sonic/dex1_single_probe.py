"""Single bounded DDS gripper diagnostic. Never publishes robot LowCmd."""
import argparse,json,math,time,threading
from pathlib import Path

def plan(q):
    if not math.isfinite(q) or not 0<=q<=5.2:raise ValueError('start position outside approved probe range')
    return {'topic':'rt/dex1/left/cmd','start_q':q,'target_q':q+.2,'step_rad':.004,'period_s':.02,'hold_s':2.,'kp':5.,'kd':.05}

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize,ChannelPublisher,ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorCmds_,MotorStates_
    from unitree_sdk2py.idl.default import unitree_go_msg_dds__MotorCmd_
    ChannelFactoryInitialize(0,'enp4s0');lock=threading.Lock();state={};subs=[]
    def receive(side,msg):
        if msg.states:
            m=msg.states[0]
            with lock:state[side]={'q':float(m.q),'dq':float(m.dq),'tau':float(m.tau_est),'at':time.monotonic()}
    for side in ('left','right'):
        s=ChannelSubscriber('rt/dex1/'+side+'/state',MotorStates_);s.Init(lambda m,k=side:receive(k,m),10);subs.append(s)
    def fresh():
        with lock:d={k:dict(v) for k,v in state.items()}
        if set(d)!={'left','right'} or any(time.monotonic()-x['at']>.25 or not all(math.isfinite(x[k]) for k in ('q','dq','tau')) for x in d.values()):raise RuntimeError('missing/stale/nonfinite gripper feedback')
        return d
    end=time.monotonic()+12
    while True:
        try:before=fresh();break
        except RuntimeError:
            if time.monotonic()>=end:
                print('Feedback discovery timeout; no command publisher created; snapshot='+json.dumps(state),flush=True)
                raise
            time.sleep(.05)
    proposal=plan(before['left']['q']);out=Path(a.output)
    report={'plan':proposal,'before':before,'execute':a.execute,'physical_side_verified':False,'samples':[]}
    out.write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('plan','before','execute')}),flush=True)
    pub=None
    try:
        if a.execute:
            pub=ChannelPublisher(proposal['topic'],MotorCmds_);pub.Init()
            for i in range(151):
                d=fresh();q=proposal['start_q']+.004*min(i,50)
                if abs(d['left']['q']-proposal['start_q'])>.4 or abs(d['left']['tau'])>1.5:raise RuntimeError('probe response/torque exceeded conservative diagnostic envelope')
                m=unitree_go_msg_dds__MotorCmd_();m.q=q;m.dq=0.;m.tau=0.;m.kp=5.;m.kd=.05
                msg=MotorCmds_();msg.cmds=[m]
                # Unitree Write() without timeout does not require any reader.
                # Establish a matched reader with the no-motion first sample.
                if pub.Write(msg,timeout=5. if i==0 else .1) is False:raise RuntimeError('DDS command subscriber not matched/write failed')
                if i==0:report['command_subscriber_matched']=True
                report['samples'].append({'at':time.monotonic(),'command_q':q,'state':d});time.sleep(.02)
            report['after']=fresh();report['result']='COMMAND_SEQUENCE_COMPLETED_PHYSICAL_OBSERVATION_REQUIRED'
    except BaseException as e:report['result']='ABORTED';report['error']=str(e);raise
    finally:
        out.write_text(json.dumps(report,indent=2))
        if pub:pub.Close()
        for s in subs:s.Close()
if __name__=='__main__':main()
