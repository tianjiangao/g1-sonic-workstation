"""Read-only callback schema audit. Never writes a device control command."""
import ctypes as C
import json
from pathlib import Path
import threading
import time
from sim_teleop.runner import ROOT

class State(C.Structure):
    _fields_=[('devID',C.c_char*32),('stateJson',C.c_char*16352)]

def main():
    lib=C.CDLL(str(ROOT/'external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64/lib/libPXREARobotSDK.so'))
    callback_type=C.CFUNCTYPE(None,C.c_void_p,C.c_int,C.c_int,C.c_void_p)
    lock=threading.Lock();summary={'packets':0,'body_packets':0,'errors':0,'pose_changes':[0]*24,'timestamp_changes':[0]*24}
    previous=None;previous_t=None
    def callback(_,typ,status,ptr):
        nonlocal previous,previous_t
        if typ!=(1<<25):return
        try:
            data=json.loads(C.cast(ptr,C.POINTER(State)).contents.stateJson)
            value=json.loads(data['value']);body=value.get('Body')
            with lock:
                summary['packets']+=1
                if not body:return
                summary['body_packets']+=1
                joints=body.get('joints',[])
                poses=[j.get('p') for j in joints];ts=[j.get('t') for j in joints]
                summary.update(body_keys=sorted(body),joint_count=len(joints),joint_keys=[sorted(j) for j in joints],
                               body_timestamp=body.get('timeStampNs'),body_dt=body.get('dt'),body_flags=body.get('flags'),
                               envelope_timestamp=value.get('timeStampNs'),joint_timestamps=ts)
                if previous and len(poses)==24:
                    for i,(p,t) in enumerate(zip(poses,ts)):
                        summary['pose_changes'][i]+=p!=previous[i]
                        summary['timestamp_changes'][i]+=t!=previous_t[i]
                previous=poses;previous_t=ts
        except Exception:
            summary['errors']+=1
    cb=callback_type(callback)
    lib.PXREAInit.argtypes=[C.c_void_p,callback_type,C.c_uint]
    if lib.PXREAInit(None,cb,1<<25)!=0:raise RuntimeError('SDK init failed')
    try:time.sleep(6)
    finally:lib.PXREADeinit()
    output=ROOT/'sim_teleop/evidence/raw-sdk-schema.json'
    output.write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='joint_keys'},indent=2))

if __name__=='__main__':main()
