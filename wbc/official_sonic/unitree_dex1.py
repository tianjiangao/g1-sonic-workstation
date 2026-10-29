"""Reuse the pinned official Dex1 loop without Dex3 retargeting dependencies.

Only the exact upstream class definitions are loaded, after SHA256 verification.
The upstream constructor would publish immediately and wait indefinitely for
state. Our adapter supplies fresh state and gated publishers instead; the actual
control_thread / ctrl_dual_gripper are unchanged. SampledFilter advances the
same pinned filter's history on repeated inputs, avoiding endpoint residuals.
"""
import ast
import hashlib
import json
import logging
import multiprocessing as mp
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import numpy as np
from official_sonic.console.backend import ROOT

def load_official():
    vendor=ROOT/'official_sonic/vendor/xr_teleoperate'
    lock=json.loads((ROOT/'official_sonic/profiles/dex1-upstream-lock.json').read_text())
    for name,digest in lock['files'].items():
        if hashlib.sha256((vendor/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Unitree official source hash mismatch: '+name)
    namespace={'np':np,'time':time,'logger_mp':logging.getLogger('unitree.dex1')}
    for file,name in [('teleop/utils/weighted_moving_filter.py','WeightedMovingFilter'),
                      ('teleop/robot_control/robot_hand_unitree.py','Dex1_1_Gripper_Controller')]:
        tree=ast.parse((vendor/file).read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(vendor/file),'exec'),namespace)
    return namespace

class SampledFilter:
    """Use the official weights at each timestep, including repeated targets."""
    def __init__(self,official):self.official=official
    def add_data(self,value):
        f=self.official
        if f._data_queue and np.array_equal(value,f._data_queue[-1]):
            if len(f._data_queue)>=f._window_size:f._data_queue.pop(0)
            f._data_queue.append(np.array(value,copy=True))
            f._filtered_data=f._apply_filter()
        else:f.add_data(value)
    @property
    def filtered_data(self):return self.official.filtered_data

class OfficialLoop:
    def __init__(self,publish):
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorCmds_
        from unitree_sdk2py.idl.default import unitree_go_msg_dds__MotorCmd_
        ns=load_official();ns.update(MotorCmds_=MotorCmds_,unitree_go_msg_dds__MotorCmd_=unitree_go_msg_dds__MotorCmd_)
        cls=ns['Dex1_1_Gripper_Controller'];self.controller=cls.__new__(cls)
        self.left=mp.Value('d',6.);self.right=mp.Value('d',6.)
        self.left_state=mp.Value('d',0.);self.right_state=mp.Value('d',0.);self.ready=mp.Value('b',False)
        self.lock=threading.Lock();self.trace_lock=mp.Lock();self.state_out=mp.Array('d',2,lock=False);self.action_out=mp.Array('d',2,lock=False)
        c=self.controller;c.fps=200.;c.simulation_mode=False;c.smooth_filter=SampledFilter(ns['WeightedMovingFilter'](np.array([.5,.3,.2]),2))
        c.LeftGripperCmb_publisher=SimpleNamespace(Write=lambda msg:publish('left',msg))
        c.RightGripperCmb_publisher=SimpleNamespace(Write=lambda msg:publish('right',msg))
        self.thread=threading.Thread(target=c.control_thread,args=(self.left,self.right,self.left_state,self.right_state,
            self.trace_lock,self.state_out,self.action_out,self.ready),daemon=True)
    def start(self):self.thread.start()
    def stop(self):
        self.ready.value=False;self.controller.running=False
        if self.thread.ident:self.thread.join(timeout=2)
    def set_state(self,side,q):
        value=self.left_state if side=='left' else self.right_state
        with value.get_lock():value.value=q
    def set_input(self,left,right,ready):
        for value,x in ((self.left,left),(self.right,right)):
            with value.get_lock():value.value=x
        with self.ready.get_lock():self.ready.value=ready
