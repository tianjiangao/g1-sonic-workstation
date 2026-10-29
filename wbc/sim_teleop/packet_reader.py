"""Atomic PXREA callbacks: never reuse partial-body SDK cache or fabricate timestamps.

This client sends no Body timestamp and only a head IMU timestamp. For t==0,
require observed pose-content updates for EACH joint. This intentionally stops
on a perfectly static/quantized joint; envelope/head advancement alone never
qualifies a body frame. Original t values remain in evidence.
"""
import ctypes as C
import fcntl
import json
import math
import os
from pathlib import Path
import threading
import time
import numpy as np
from gear_sonic.utils.teleop.body_freshness import valid_body_pose
from sim_teleop.runner import ROOT,write_json

class PacketGate:
    def __init__(self,stale_s=.25):
        self.stale_s=stale_s;self.reason='warming_up';self.sample=None
        self.previous=None;self.committed=None;self.last_source=0;self.changed_at=[None]*24
        self.last_t=None;self.committed_t=None;self.imu_at=[None]*24
        self.count=0;self.accepted=0;self.invalid=0;self.changes=[0]*24;self.missing_t=[]
        self.first=None;self.last=None;self.source_backwards=0;self.max_gap=0;self.last_accept=None
    def reject(self,reason):
        self.reason=reason;self.sample=None;self.invalid+=1
        return None
    def update(self,value,now=None):
        now=time.monotonic() if now is None else now;self.count+=1
        try:
            stamp=value['timeStampNs'];joints=value['Body']['joints']
            if isinstance(stamp,bool) or not isinstance(stamp,int) or stamp<=0 or len(joints)!=24:
                return self.reject('invalid_packet_schema')
            pose=np.array([[float(v) for v in j['p'].split(',')] for j in joints])
            t=tuple(j.get('t',0) for j in joints)
            if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in t):return self.reject('invalid_imu_timestamp')
            if not valid_body_pose(pose):return self.reject('invalid_pose_quaternion')
            if np.max(np.abs(pose[:,:3]))>100:return self.reject('position_out_of_range_meters')
            if stamp<=self.last_source:
                self.source_backwards+=int(stamp<self.last_source)
                return self.reject('replayed_or_backward_source_timestamp')
            self.last_source=stamp;self.last=now;self.missing_t=[i for i,v in enumerate(t) if v==0]
            if self.first is None:self.first=now
            if self.previous is None:
                self.previous=pose.copy();self.committed=pose.copy();self.last_t=t;self.committed_t=t
                self.changed_at=[now]*24;self.imu_at=[now]*24
                return None
            changed=np.any(pose!=self.previous,axis=1)
            for i,flag in enumerate(changed):
                if flag:self.changed_at[i]=now;self.changes[i]+=1
                if t[i]>0:
                    if t[i]<self.last_t[i]:return self.reject('backward_imu_timestamp')
                    if t[i]>self.last_t[i]:self.imu_at[i]=now
            self.previous=pose.copy();self.last_t=t
            if any(now-v>=self.stale_s for v in self.changed_at):return self.reject('stale_joint_content')
            if any(t[i]>0 and now-self.imu_at[i]>=self.stale_s for i in range(24)):
                return self.reject('stale_joint_imu')
            if not np.all(np.any(pose!=self.committed,axis=1)):
                self.reason='awaiting_all_joint_content_update';return None
            if any(t[i]>0 and t[i]<=self.committed_t[i] for i in range(24)):
                self.reason='awaiting_all_available_imu_update';return None
            dt=now-self.last_accept if self.last_accept is not None else 0
            self.max_gap=max(self.max_gap,dt);self.last_accept=now;self.accepted+=1
            self.committed=pose.copy();self.committed_t=t;self.reason='ready'
            self.sample={'body_poses_np':pose.copy(),'joint_timestamps_ns':t,'source_packet_timestamp_ns':stamp,
                         'joint_received_monotonic':tuple(self.changed_at),'timestamp_ns':int(now*1e9),
                         'timestamp_monotonic':now,'timestamp_realtime':time.time(),'dt':dt,'fps':1/dt if dt else 0}
            return self.sample
        except (KeyError,TypeError,ValueError,OverflowError):return self.reject('invalid_packet_schema')
    def latest(self,now=None):
        now=time.monotonic() if now is None else now
        if (self.sample is not None and now-self.sample['timestamp_monotonic']>=self.stale_s) or (
            self.previous is not None and any(now-v>=self.stale_s for v in self.changed_at)):
            self.reject('stale_complete_frame_or_joint')
        return self.sample
    def stats(self):
        return {'reason':self.reason,'packets':self.count,'accepted_frames':self.accepted,'invalid_packets':self.invalid,
                'joint_content_change_counts':self.changes,'missing_imu_timestamp_indices':self.missing_t,
                'last_original_joint_timestamps':self.last_t,'source_backwards':self.source_backwards,
                'last_packet_age_s':time.monotonic()-self.last if self.last is not None else None,
                'joint_content_age_s':[time.monotonic()-v if v is not None else None for v in self.changed_at],
                'max_accepted_frame_gap_s':self.max_gap,'stale_s':self.stale_s,
                'freshness_basis':'atomic complete body packet + advancing source envelope + EACH joint content update + each available IMU timestamp',
                'limitation':'Zero IMU timestamps remain unknown; perfectly static joint content intentionally causes stop'}

class State(C.Structure):
    _fields_=[('devID',C.c_char*32),('stateJson',C.c_char*16352)]

class AtomicPicoReader:
    start_after_setup=True
    def __init__(self,output=None):
        self.gate=PacketGate();self.lock=threading.Lock();self.stop_event=threading.Event()
        self.freshness_stale_s=.25;self.fault=False;self.latch_reason=None;self.ever_ready=False;self.output=Path(output) if output else None
        self.controllers={};self.sdk=self;self.callback_type=C.CFUNCTYPE(None,C.c_void_p,C.c_int,C.c_int,C.c_void_p)
        self.lib=C.CDLL(str(ROOT/'external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64/lib/libPXREARobotSDK.so'))
        self.callback=self.callback_type(self._callback);self.opened=False
    def _callback(self,_,typ,status,ptr):
        if typ!=(1<<25):return
        try:
            data=json.loads(C.cast(ptr,C.POINTER(State)).contents.stateJson)
            if data.get('functionName')!='Tracking':return
            value=json.loads(data['value'])
            with self.lock:
                if 'Body' not in value:return
                sample=self.gate.update(value)
                if sample is not None:
                    # Bind controllers to this accepted body frame. Later SDK
                    # callbacks can replace self.controllers before IPC reads it.
                    sample['pico_controllers']=value.get('Controller',{})
                # Same packet contains both body and controller data.
                self.controllers=value.get('Controller',{}) if sample is not None else {}
                if sample is not None:self.ever_ready=True
                elif self.ever_ready and self.gate.reason not in ('awaiting_all_joint_content_update','awaiting_all_available_imu_update'):
                    self.fault=True;self.latch_reason=self.latch_reason or self.gate.reason
        except Exception:
            with self.lock:
                self.gate.reject('callback_parse_failure')
                if self.ever_ready:self.fault=True;self.latch_reason=self.latch_reason or self.gate.reason
    def start(self):
        path=Path(os.environ.get('XDG_RUNTIME_DIR',f'/tmp/sonic-{os.getuid()}'))/'sonic-xrt.lock'
        path.parent.mkdir(parents=True,exist_ok=True);self.session_lock=path.open('a')
        fcntl.flock(self.session_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.lib.PXREAInit.argtypes=[C.c_void_p,self.callback_type,C.c_uint]
        if self.lib.PXREAInit(None,self.callback,1<<25)!=0:raise RuntimeError('PXREAInit failed')
        self.opened=True
        self.thread=threading.Thread(target=self._watch,daemon=True);self.thread.start()
    def _watch(self):
        while not self.stop_event.wait(.05):
            self.get_latest()
            if self.output:write_json(self.output,self.freshness_stats())
    def get_latest(self):
        with self.lock:
            sample=self.gate.latest()
            if self.ever_ready and sample is None and self.gate.reason.startswith('stale'):
                self.fault=True;self.latch_reason=self.latch_reason or self.gate.reason
            return None if self.fault else sample
    @property
    def disconnected(self):
        self.get_latest();return self.fault
    def get_timestamp_ns(self):
        s=self.get_latest();return s['timestamp_ns'] if s is not None else 0
    def freshness_stats(self):
        with self.lock:return dict(self.gate.stats(),fault_latched=self.fault,latch_reason=self.latch_reason,observed_monotonic=time.monotonic())
    def stop(self):
        self.stop_event.set()
        if hasattr(self,'thread'):self.thread.join(timeout=1)
        if self.opened:self.lib.PXREADeinit();self.opened=False
        if hasattr(self,'session_lock'):self.session_lock.close()
    def wait_ready(self,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if self.disconnected:raise RuntimeError('PICO fault: '+self.gate.reason)
            if self.get_latest() is not None and self.gate.accepted>=20:return
            time.sleep(.02)
        raise RuntimeError('PICO not ready: '+self.gate.reason)
    def __getattr__(self,name):
        # Official streamer reads these controller getters; no device writes exposed.
        mapping={'get_A_button':('right','primaryButton'),'get_B_button':('right','secondaryButton'),
                 'get_X_button':('left','primaryButton'),'get_Y_button':('left','secondaryButton')}
        for side in ('left','right'):
            for suffix,key in [('trigger','trigger'),('grip','grip'),('menu_button','menuButton'),('axis_click','axisClick')]:
                mapping[f'get_{side}_{suffix}']=(side,key)
        if name in mapping:
            side,key=mapping[name]
            def get():
                with self.lock:return self.controllers.get(side,{}).get(key,0)
            return get
        if name in ('get_left_axis','get_right_axis'):
            side=name.split('_')[1]
            def get_axis():
                with self.lock:
                    c=self.controllers.get(side,{});return [c.get('axisX',0),c.get('axisY',0)]
            return get_axis
        raise AttributeError(name)
