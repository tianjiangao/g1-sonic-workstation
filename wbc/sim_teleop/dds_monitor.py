"""Read-only DDS evidence and fail-stop monitor, confined to private netns."""
import argparse
import json
import math
from pathlib import Path
import threading
import time
import mujoco
import numpy as np
from sim_teleop.safety import assert_isolated
from sim_teleop.runner import ROOT,write_json


def main():
    assert_isolated()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize,ChannelSubscriber
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_,LowState_
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    model=mujoco.MjModel.from_xml_path(str(ROOT/'gear_sonic/data/robot_model/model_data/g1/scene_43dof.xml'))
    limits=[];names=[]
    for i in range(model.nu):
        j=model.actuator_trnid[i,0]
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,j)
        if '_hand_' in name:continue
        names.append(mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,j))
        limits.append(tuple(model.jnt_range[j]) if model.jnt_limited[j] else (-float('inf'),float('inf')))
    assert len(names)==29, names
    counts={'lowcmd':0,'lowstate':0};last={};first={};gaps={k:[] for k in counts};faults=[]
    q0={};span={};lock=threading.Lock();start=time.monotonic()
    def receive(kind,msg):
        now=time.monotonic()
        with lock:
            if kind in last:gaps[kind].append(now-last[kind]);gaps[kind]=gaps[kind][-10000:]
            last[kind]=now;first.setdefault(kind,now);counts[kind]+=1
            motors=msg.motor_cmd if kind=='lowcmd' else msg.motor_state
            q=[float(m.q) for m in motors[:29]]
            vals=[v for m in motors[:29] for v in ([m.q,m.dq,m.kp,m.kd,m.tau] if kind=='lowcmd' else [m.q,m.dq,m.tau_est])]
            if not all(math.isfinite(v) for v in vals):faults.append(kind+':nonfinite')
            if kind=='lowcmd':
                for i,(v,(lo,hi)) in enumerate(zip(q,limits)):
                    if v<lo-.01 or v>hi+.01:faults.append(f'command_limit:{i}:{v}:{lo}:{hi}')
            if kind not in q0:q0[kind]=q
            span[kind]=max(span.get(kind,0),max(abs(v-z) for v,z in zip(q,q0[kind])))
    ChannelFactoryInitialize(0,'lo')
    subscribers=[]
    for kind,typ in [('lowcmd',LowCmd_),('lowstate',LowState_)]:
        sub=ChannelSubscriber('rt/'+kind,typ);sub.Init(lambda msg,k=kind:receive(k,msg),10);subscribers.append(sub)
    while True:
        assert_isolated()
        now=time.monotonic()
        with lock:
            summary={'elapsed_s':now-start,'counts':dict(counts),'joint_names_hardware_order':names,
                     'max_joint_change_rad':dict(span),'faults':faults[-20:],
                     'rates_hz':{k:(len(v)/sum(v) if v and sum(v)>0 else 0) for k,v in gaps.items()},
                     'max_gap_s':{k:max(v,default=0) for k,v in gaps.items()},
                     'last_age_s':{k:now-v for k,v in last.items()}}
        write_json(Path(a.output),summary)
        if faults:raise RuntimeError('DDS numeric/limit fault: '+str(faults[-3:]))
        if now-start>60 and any(k not in last or now-last[k]>.5 for k in counts):
            raise RuntimeError('DDS missing/stale messages')
        time.sleep(.1)

if __name__=='__main__':main()
