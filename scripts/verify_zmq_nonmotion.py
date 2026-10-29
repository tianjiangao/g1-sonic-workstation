#!/usr/bin/env python3
"""Independent SONIC-format transport test. Fixed audit-only ports/topics; no DDS."""
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
import zmq
from gear_sonic.utils.teleop.zmq.zmq_planner_sender import pack_pose_message

BASE=Path('/opt/g1/workspace/audit/2026-10-26-sonic')
REMOTE=r'''
import ctypes as c,ctypes.util,json,time,struct,hashlib
lib=c.CDLL(ctypes.util.find_library('zmq'))
lib.zmq_ctx_new.restype=c.c_void_p
for name in ['zmq_socket']:
 getattr(lib,name).argtypes=[c.c_void_p,c.c_int];getattr(lib,name).restype=c.c_void_p
lib.zmq_setsockopt.argtypes=[c.c_void_p,c.c_int,c.c_void_p,c.c_size_t]
for name in ['zmq_bind','zmq_connect']:
 getattr(lib,name).argtypes=[c.c_void_p,c.c_char_p]
lib.zmq_recv.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_int]
lib.zmq_send.argtypes=[c.c_void_p,c.c_void_p,c.c_size_t,c.c_int]
lib.zmq_close.argtypes=[c.c_void_p];lib.zmq_ctx_term.argtypes=[c.c_void_p]
ctx=lib.zmq_ctx_new();sub=lib.zmq_socket(ctx,2);pub=lib.zmq_socket(ctx,1)
for s in (sub,pub):
 v=c.c_int(0);assert lib.zmq_setsockopt(s,17,c.byref(v),c.sizeof(v))==0
prefix=b'audit_pose';assert lib.zmq_setsockopt(sub,6,prefix,len(prefix))==0
v=c.c_int(200);lib.zmq_setsockopt(sub,27,c.byref(v),c.sizeof(v))
assert lib.zmq_connect(sub,b'tcp://192.168.123.99:15556')==0
assert lib.zmq_bind(pub,b'tcp://192.168.123.164:15557')==0
print('READY audit-only 15556/15557',flush=True)
buf=c.create_string_buffer(65536);deadline=time.monotonic()+15;count=0;errors=[];last=None;gaps=[];seqs=[]
try:
 while time.monotonic()<deadline:
  n=lib.zmq_recv(sub,buf,len(buf),0)
  if n<0:continue
  now=time.monotonic();raw=buf.raw[:n]
  try:
   assert raw.startswith(prefix)
   header=json.loads(raw[len(prefix):len(prefix)+1280].rstrip(b'\0'))
   data=raw[len(prefix)+1280:];offset=0;fields={}
   for f in header['fields']:
    num=1
    for d in f['shape']:num*=d
    code={'i64':'q','f32':'f','f64':'d','i32':'i','bool':'?'}[f['dtype']]
    size=struct.calcsize('<'+code)*num
    fields[f['name']]=struct.unpack('<'+str(num)+code,data[offset:offset+size]);offset+=size
   assert offset==len(data) and header['v']==3 and header['endian']=='le'
   assert len(fields['smpl_joints'])==360 and len(fields['smpl_pose'])==315 and len(fields['body_quat_w'])==20
   seq=int(fields['frame_index'][0])//5;count+=1;seqs.append(seq)
   if last is not None:gaps.append(now-last)
   last=now
   ack=b'audit_ack'+json.dumps({'seq':seq,'sha256':hashlib.sha256(raw).hexdigest()}).encode()
   lib.zmq_send(pub,ack,len(ack),0)
  except Exception as e:errors.append(repr(e))
finally:
 for s in (sub,pub):lib.zmq_close(s)
 lib.zmq_ctx_term(ctx)
print(json.dumps({'received':count,'parse_errors':errors,'max_interarrival_s':max(gaps,default=0),'first_seq':min(seqs,default=-1),'last_seq':max(seqs,default=-1)}),flush=True)
'''

def main():
 import hashlib
 raw=(BASE/'evidence/pose_streamer_last.bin').read_bytes()
 assert raw.startswith(b'pose')
 h=json.loads(raw[4:1284].rstrip(b'\0'));offset=1284;template={}
 for f in h['fields']:
  dt={'f32':'<f4','f64':'<f8','i32':'<i4','i64':'<i8','bool':'?'}[f['dtype']]
  size=int(np.prod(f['shape']))*np.dtype(dt).itemsize
  template[f['name']]=np.frombuffer(raw[offset:offset+size],dtype=dt).reshape(f['shape']).copy();offset+=size
 ctx=zmq.Context();pub=ctx.socket(zmq.PUB);pub.linger=0;pub.bind('tcp://192.168.123.99:15556')
 sub=ctx.socket(zmq.SUB);sub.linger=0;sub.subscribe(b'audit_ack');sub.connect('tcp://192.168.123.164:15557')
 ssh=['ssh','-S',str(BASE/'ssh-control'),'-p','22','-o','BatchMode=yes','unitree@192.168.123.164','python3 -u -']
 remote=subprocess.Popen(ssh,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 remote.stdin.write(REMOTE);remote.stdin.close()
 ready=remote.stdout.readline().strip();print(ready,flush=True)
 if not ready.startswith('READY'): raise RuntimeError('remote test failed to initialize: '+ready)
 time.sleep(.6)
 sent={};acks={};rtts=[];bad=[];phase_acks={};seq=0
 try:
  for phase in ['initial','after_gap','after_rebind']:
   if phase=='after_gap':time.sleep(1.0)
   if phase=='after_rebind':pub.close();time.sleep(.5);pub=ctx.socket(zmq.PUB);pub.linger=0;pub.bind('tcp://192.168.123.99:15556');time.sleep(.6)
   next_tick=time.monotonic();stop=next_tick+2
   while time.monotonic()<stop:
    template['frame_index']=np.arange(seq*5,seq*5+5,dtype=np.int64)
    payload=pack_pose_message(template,topic='audit_pose')
    sent[seq]=(time.monotonic(),hashlib.sha256(payload).hexdigest(),phase);pub.send(payload);seq+=1
    while sub.poll(0):
     ack=json.loads(sub.recv()[len(b'audit_ack'):]);s=ack['seq'];ts,h,ph=sent[s]
     if ack['sha256']!=h:bad.append(s)
     acks[s]=ph;rtts.append((time.monotonic()-ts)*1000)
    next_tick+=.02
    remaining=next_tick-time.monotonic()
    if remaining>0:
     # Receive promptly for RTT, rather than count intentional 20ms sender pacing.
     deadline=time.monotonic()+remaining
     while time.monotonic()<deadline:
      if sub.poll(max(1,int((deadline-time.monotonic())*1000))):
       ack=json.loads(sub.recv()[len(b'audit_ack'):]);s=ack['seq'];ts,h,ph=sent[s]
       if ack['sha256']!=h:bad.append(s)
       acks[s]=ph;rtts.append((time.monotonic()-ts)*1000)
  remote.wait(timeout=16);remote_text=remote.stdout.read();(BASE/'evidence/zmq_remote.txt').write_text(ready+'\n'+remote_text)
  result={'kind':'actual CPU PoseStreamer fields repacked on audit-only topic/ports; not controller/PICO acceptance','sent':seq,'acks':len(acks),
   'hash_mismatches':bad,'phases':{p:sum(v==p for v in acks.values()) for p in ['initial','after_gap','after_rebind']},
   'rtt_ms':{k:float(np.percentile(rtts,q)) for k,q in [('p50',50),('p95',95),('max',100)]} if rtts else {},
   'remote_exit':remote.returncode,'remote_summary':remote_text.strip()}
  remote_summary=json.loads(remote_text.strip().splitlines()[-1])
  result['status']='PASS' if remote.returncode==0 and len(acks)>=seq*.95 and not bad and not remote_summary['parse_errors'] and all(v>=90 for v in result['phases'].values()) else 'FAIL'
  (BASE/'evidence/zmq_nonmotion.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
  return 0 if result['status']=='PASS' else 1
 finally:
  pub.close();sub.close();ctx.term()
  if remote.poll() is None: remote.terminate()

if __name__=='__main__':raise SystemExit(main())
