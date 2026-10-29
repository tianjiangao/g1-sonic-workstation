"""Independent synthetic end-to-end recording and official export verification."""
import json
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from capture.record import Capture
from capture.tests.test_contract import sample
from capture.export import export_episode

root=Path(sys.argv[1]);cap=Capture(root,15,'SYNTHETIC ONLY, NOT ROBOT DATA',{'synthetic':True})
for key,value in sample().items():
    if key.startswith('camera_'):
        shape=(480,1280,3) if key=='camera_head' else (480,640,3)
        im=np.zeros(shape,np.uint8);im[:,:,1]=128
        ok,raw=cv2.imencode('.jpg',im);assert ok
        cap.ingest(key,None,raw.tobytes())
    else:cap.ingest(key,value['data'])
cap.toggle()
for i in range(6):
    now=time.monotonic_ns()
    for v in cap.latest.values():v['mono_ns']=now
    cap.next_frame=now;cap.tick();time.sleep(1/15)
cap.toggle();cap.close()
ep=root/'episode_000000';report=export_episode(ep,root/'LEROBOT_SYNTHETIC_ONLY')
assert report['frames']==6 and len(report['videos'])==3
import pyarrow.parquet as pq
f=next((root/'LEROBOT_SYNTHETIC_ONLY/data').rglob('*.parquet'));t=pq.read_table(f)
assert t['observation.dex1'][0].as_py()==[1.,2.]
assert t['action.dex1'][0].as_py()==[3.,4.]
assert len(t['observation.body'][0].as_py())==29
print('PASS: synthetic raw -> official LeRobot -> parquet/video independent readback')
