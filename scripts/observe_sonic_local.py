#!/usr/bin/env python3
"""Receive only from isolated loopback Manager :15566. No robot connection."""
import argparse,collections,json,time
import zmq

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=float,default=30);a=p.parse_args()
    ctx=zmq.Context();s=ctx.socket(zmq.SUB);s.linger=0
    topics=[b'pose',b'planner',b'command',b'manager_state']
    for t in topics:s.subscribe(t)
    s.connect('tcp://127.0.0.1:15566');counts=collections.Counter();errors=[];start=time.monotonic()
    try:
        while time.monotonic()-start<a.seconds:
            if not s.poll(100):continue
            raw=s.recv();topic=next(t for t in topics if raw.startswith(t));counts[topic.decode()]+=1
            try:
                header=json.loads(raw[len(topic):len(topic)+1280].rstrip(b'\0'))
                sizes={'bool':1,'u8':1,'f32':4,'f64':8,'i32':4,'i64':8};n=0
                for f in header['fields']:
                    size=sizes[f['dtype']]
                    for dim in f['shape']:size*=dim
                    n+=size
                assert len(raw)==len(topic)+1280+n
            except Exception as e:errors.append(repr(e))
        result={'counts':dict(counts),'decode_errors':errors,'status':'PASS' if counts['pose']>1 and not errors else 'PARTIAL',
                'note':'OFF only publishes manager_state; isolated button calibration and POSE mode needed for pose frames'}
        print(json.dumps(result,indent=2));return 0 if result['status']=='PASS' else 2
    finally:s.close();ctx.term()
if __name__=='__main__':raise SystemExit(main())
