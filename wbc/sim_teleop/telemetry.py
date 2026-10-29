"""Capture PICO ZMQ and SONIC inference evidence inside isolated simulation."""
import argparse
import json
from pathlib import Path
import time
import msgpack
import numpy as np
import zmq
from sim_teleop.safety import assert_isolated
from sim_teleop.runner import write_json

def decode(message,topic):
    head=json.loads(message[len(topic):len(topic)+1280].rstrip(b'\0'));at=len(topic)+1280;result={}
    types={'f32':'<f4','f64':'<f8','i32':'<i4','i64':'<i8','u8':'u1','bool':'?'}
    for f in head['fields']:
        dtype=np.dtype(types[f['dtype']]);n=int(np.prod(f['shape']));size=n*dtype.itemsize
        v=np.frombuffer(message[at:at+size],dtype=dtype).reshape(f['shape']);at+=size
        if v.dtype.kind=='f' and not np.isfinite(v).all():raise ValueError('nonfinite ZMQ '+f['name'])
        result[f['name']]=v
    if at!=len(message):raise ValueError('packet length mismatch')
    return result

class PoseWatchdog:
    def __init__(self):self.active=False;self.entered=None;self.last=None
    def mode(self,value,now):
        if value==1 and not self.active:self.entered=now;self.last=None
        self.active=value==1
    def pose(self,now):self.last=now
    def expired(self,now):
        origin=self.last if self.last is not None else self.entered
        return self.active and origin is not None and now-origin>.5

def main():
    assert_isolated();p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    path=Path(a.output);ctx=zmq.Context();sockets=[];poll=zmq.Poller()
    for port in (5556,5557):
        s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,b'');s.setsockopt(zmq.RCVHWM,500)
        s.connect(f'tcp://127.0.0.1:{port}');poll.register(s,zmq.POLLIN);sockets.append(s)
    counts={};latency=[];first=time.monotonic();last_save=first;last_pose_index=None;gaps=0;last_pose_at=None;last_debug_at=None
    trace=path.with_suffix('.jsonl').open('a',buffering=1)
    mode=None;sample_index=0;watchdog=PoseWatchdog()
    while True:
        now=time.monotonic()
        for sock,_ in poll.poll(50):
            data=sock.recv();topic=next((v for v in (b'manager_state',b'robot_config',b'g1_debug',b'command',b'planner',b'pose') if data.startswith(v)),None)
            if topic is None:continue
            key=topic.decode();counts[key]=counts.get(key,0)+1
            if topic in (b'g1_debug',b'robot_config'):
                d=msgpack.unpackb(data[len(topic):],raw=False)
                if topic==b'g1_debug':
                    last_debug_at=now;sample_index+=1
                    if sample_index==1:(path.parent/'policy-active').write_text(str(now))
                    if sample_index%2==0:trace.write(json.dumps({'host_monotonic':now,'topic':key,'data':d})+'\n')
            else:
                d=decode(data,topic)
                if topic==b'pose':
                    watchdog.pose(now)
                    last_pose_at=now
                    if 'timestamp_monotonic' in d:latency.append(now-float(d['timestamp_monotonic'][0]));latency=latency[-10000:]
                    index=int(d['frame_index'][-1])
                    if last_pose_index is not None and index>last_pose_index+1:gaps+=index-last_pose_index-1
                    last_pose_index=index
                    trace.write(json.dumps({'host_monotonic':now,'topic':key,'data':{k:v.tolist() for k,v in d.items()}})+'\n')
                if topic==b'manager_state':
                    mode=int(d['stream_mode'][0]);watchdog.mode(mode,now)
                if topic==b'command':
                    trace.write(json.dumps({'host_monotonic':now,'topic':key,'data':{k:v.tolist() for k,v in d.items()}})+'\n')
                    if bool(d.get('stop',[False])[0]):
                        write_json(path.parent/'operator-stop.json',{'source':'ZMQ command stop','host_monotonic':now})
        if now-last_save>=.5:
            summary={'elapsed_s':now-first,'topic_counts':counts,'stream_mode':mode,'pose_frame_index_gaps':gaps,
                     'pose_receipt_to_zmq_ms':{k:float(np.percentile(latency,v)*1000) for k,v in [('p50',50),('p95',95),('p99',99)]} if latency else {},
                     'last_pose_age_s':now-last_pose_at if last_pose_at else None,
                     'last_inference_debug_age_s':now-last_debug_at if last_debug_at else None}
            write_json(path,summary);last_save=now
        # Full-body stream pause/disconnect must not silently hold an old target.
        if watchdog.expired(now):
            raise RuntimeError('POSE stream timeout; fail-stop simulation')

if __name__=='__main__':main()
