#!/usr/bin/env python3
"""CPU-only SMPL, FK and PoseStreamer verification using an in-memory sink."""
import json,time
from pathlib import Path
from unittest.mock import patch
import numpy as np
from gear_sonic.scripts import pico_manager_thread_server as m

class Reader:
    def __init__(self):self.i=0
    def get_latest(self):
        self.i+=1;p=np.zeros((24,7));p[:,6]=1
        return {'body_poses_np':p,'timestamp_ns':self.i*20_000_000,'fps':50.,'dt':.02,
                'timestamp_monotonic':time.monotonic()}
    def get_timestamp_ns(self):return self.i*20_000_000
class Sink:
    def __init__(self):self.messages=[]
    def send(self,message):self.messages.append(message)

def main():
    sink=Sink();reader=Reader();tp=m.ThreePointPose()
    try:
        streamer=m.PoseStreamer(socket=sink,reader=reader,three_point=tp,num_frames_to_send=5,
                                target_fps=50,use_cuda=False,record_dir='',record_format='npz')
        with patch.object(m,'get_controller_inputs',return_value=(False,0.,0.,0.,0.)),patch.object(m,'get_abxy_buttons',return_value=(False,False,False,False)):
            for _ in range(30):streamer.run_once()
        assert len(sink.messages)>5
        summaries=[]
        for raw in sink.messages:
            assert raw.startswith(b'pose')
            h=json.loads(raw[4:1284].rstrip(b'\0'));offset=1284;fields={}
            for f in h['fields']:
                dt={'f32':'<f4','f64':'<f8','i32':'<i4','i64':'<i8','bool':'?'}[f['dtype']]
                size=int(np.prod(f['shape']))*np.dtype(dt).itemsize
                v=np.frombuffer(raw[offset:offset+size],dtype=dt).reshape(f['shape'])
                assert np.isfinite(v).all();fields[f['name']]=list(v.shape);offset+=size
            assert offset==len(raw)
            summaries.append(fields)
        Path('/opt/g1/workspace/audit/2026-10-26-sonic/evidence/pose_streamer_last.bin').write_bytes(sink.messages[-1])
        result={'status':'PASS','input':'synthetic identity quaternions, CPU only','transport':'in-memory sink; no ZMQ socket/DDS',
                'pose_messages':len(sink.messages),'last_fields':summaries[-1],'note':'does not certify human-to-robot calibration or real motion'}
        Path('/opt/g1/workspace/audit/2026-10-26-sonic/evidence/pose_streamer_offline.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:tp.close()
if __name__=='__main__':main()
