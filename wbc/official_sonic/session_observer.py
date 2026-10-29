"""Passive ZMQ acceptance evidence. Not a training-dataset exporter."""
import argparse
import json
from pathlib import Path
import time
import msgpack
import zmq
from sim_teleop.telemetry import decode
from official_sonic.thermal_monitor import ThermalMonitor

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--seconds',type=float,default=900);a=p.parse_args()
    ctx=zmq.Context();poll=zmq.Poller();sockets=[];counts={};last={};path=Path(a.output)
    for endpoint in ('tcp://192.168.123.99:5556','tcp://192.168.123.164:5557'):
        s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,b'');s.setsockopt(zmq.RCVHWM,2000);s.connect(endpoint);poll.register(s,zmq.POLLIN);sockets.append(s)
    start=time.monotonic();saved=start;monitor=ThermalMonitor();thermal=None
    try:
        with path.with_suffix('.jsonl').open('a',buffering=1) as f:
            while time.monotonic()-start<a.seconds:
                for sock,_ in poll.poll(50):
                    raw=sock.recv();now=time.monotonic()
                    topic=next((t for t in (b'manager_state',b'robot_config',b'g1_debug',b'command',b'planner',b'pose') if raw.startswith(t)),None)
                    if topic is None:continue
                    name=topic.decode();counts[name]=counts.get(name,0)+1;last[name]=now
                    d=msgpack.unpackb(raw[len(topic):],raw=False) if topic in (b'robot_config',b'g1_debug') else {k:v.tolist() for k,v in decode(raw,topic).items()}
                    if topic==b'g1_debug':
                        try:thermal=monitor.update(d,now)
                        except ValueError as e:thermal={'available':False,'reason':str(e)}
                    if topic!=b'manager_state':f.write(json.dumps({'host_monotonic':now,'host_epoch':time.time(),'topic':name,'data':d})+'\n')
                now=time.monotonic()
                if now-saved>=.5:
                    temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'counts':counts,'elapsed_s':now-start,'last_age_s':{k:now-v for k,v in last.items()},'thermal':thermal,'training_dataset':False},indent=2));temp.replace(path);saved=now
    finally:
        for s in sockets:s.close()
        ctx.term()

if __name__=='__main__':main()
