"""Passive ZMQ and DDS subscriber. No publishers or control startup code."""
import argparse
import fcntl
import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import queue
import select
import shutil
import signal
import sys
import threading
import time
import cv2
import msgpack
import numpy as np
import zmq
from capture.core import CAMERAS, Episode, make_frame
from capture import batches
from capture.sonic_camera import packets

WBC=Path('/opt/g1/GR00T-WholeBodyControl')

def shutdown_outcome(status,requested,interrupted_recording=False):
    """Separate process termination from stream readiness; never approve data."""
    failed=bool(status.get('faults')) or interrupted_recording
    success=not failed and (requested or bool(status.get('ready')))
    return {'exit_code':0 if success else 2,'shutdown_requested':requested,
            'stream_ready_at_exit':bool(status.get('ready')),
            'interrupted_recording':interrupted_recording,
            'faults':status.get('faults',{}),
            'classification':'normal_stop' if success and requested else 'ready_end' if success else 'capture_failure',
            'saved_episodes':status.get('saved_episodes',0),'training_acceptance':False}

def unpack(raw,topic):
    header=json.loads(raw[len(topic):len(topic)+1280].rstrip(b'\0'))
    if header.get('endian','le')!='le':raise ValueError('unsupported byte order')
    at=len(topic)+1280;result={}
    types={'f32':'<f4','f64':'<f8','i32':'<i4','i64':'<i8','bool':'?','u8':'u1'}
    for f in header['fields']:
        dtype=np.dtype(types[f['dtype']]);n=int(np.prod(f['shape']));size=n*dtype.itemsize
        value=np.frombuffer(raw[at:at+size],dtype=dtype).reshape(f['shape']);at+=size
        if value.dtype.kind=='f' and not np.isfinite(value).all():raise ValueError('nonfinite input')
        result[f['name']]=value.tolist()
    if at!=len(raw):raise ValueError('packet length mismatch')
    return result

class Capture:
    def __init__(self,root,fps,task,manifest):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.fps=fps;self.task=task;self.latest={};self.ep=None;self.index=0
        self.counts=Counter();self.faults=Counter();self.images={};self.last_toggle=False
        self.announce=lambda text: print('播报：'+text,flush=True)
        self.batch_id=batches.state(self.root.parent)['batch_id']
        self.record_started_ns=None;self.last_frames=0;self.last_duration_s=0.;self.last_event=None;self.saved_episodes=0;self.take_number=None;self.last_saved_path=None
        self.next_frame=0;self.manifest=dict(manifest,fps=fps,task=task)
        (self.root/'session.json').write_text(json.dumps(self.manifest,indent=2))
    def ingest(self,key,data,raw=None,mono_ns=None,epoch_ns=None):
        mono_ns=time.monotonic_ns() if mono_ns is None else mono_ns
        epoch_ns=time.time_ns() if epoch_ns is None else epoch_ns
        if key in CAMERAS:
            image=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
            expected=(480,1280,3) if key=='camera_head' else (480,640,3)
            if image is None or image.shape!=expected:raise ValueError('invalid camera shape '+key)
            digest=hashlib.sha256(raw).hexdigest();path='images/'+digest+'.jpg'
            data={'path':path,'shape':list(image.shape),'sha256':digest,'capture_timestamp':(data or {}).get('capture_timestamp')}
            self.images[key]=raw
        self.latest[key]={'data':data,'mono_ns':mono_ns,'epoch_ns':epoch_ns};self.counts[key]+=1
        if self.ep:
            event={'topic':key,**self.latest[key]}
            if raw is not None and key not in CAMERAS:event['raw_base64']=base64.b64encode(raw).decode()
            if key in CAMERAS:
                p=self.ep.path/data['path']
                if not p.exists():p.write_bytes(raw)
            self.ep.events.write(json.dumps(event,allow_nan=False)+'\n')
    def toggle(self):
        if self.ep:
            path=self.ep.path;frames=self.ep.count;self.last_frames=frames;self.last_duration_s=(time.monotonic_ns()-self.record_started_ns)/1e9;self.ep.close('operator_stop');self.ep=None
            meta=json.loads((path/'episode.json').read_text());meta['take_number']=self.take_number;meta['batch_id']=self.batch_id
            (path/'episode.json').write_text(json.dumps(meta,indent=2))
            if meta['complete']:
                self.saved_episodes+=1;self.last_saved_path=str(path)
                self.notify('saved',f'采集结束，第{self.take_number}条已保存')
            else:self.notify('incomplete','采集结束，但没有有效帧，未保存为有效片段')
            print('SAVED',path,'complete=',meta['complete'],flush=True);return
        now=time.monotonic_ns()
        make_frame(self.latest,now)  # refuse incomplete startup
        counter=batches.allocate(self.root.parent)
        self.take_number=counter['last_number'];self.batch_id=counter['batch_id']
        self.ep=Episode(self.root/f'episode_{self.index:06d}');self.index+=1;self.next_frame=now;self.record_started_ns=now
        (self.ep.path/'context.json').write_text(json.dumps({'session':self.manifest,'latest':self.latest},allow_nan=False))
        for key,raw in self.images.items():
            (self.ep.path/self.latest[key]['data']['path']).write_bytes(raw)
        print('RECORDING',self.ep.path,flush=True)
        self.notify('recording',f'开始采集，第{self.take_number}条')
    def notify(self,kind,text):
        self.last_event={'kind':kind,'text':text,'at_ns':time.time_ns(),'take_number':self.take_number}
        self.announce(text)
    def request(self,action):
        try:
            if action=='finish_batch':
                if self.ep:self.toggle()
                batches.finish(self.root.parent)
                self.batch_id=batches.state(self.root.parent)['batch_id'];self.take_number=None;self.saved_episodes=0
                self.last_frames=0;self.last_duration_s=0.;self.last_saved_path=None
                self.notify('batch_finished','本批次已结束；下次从第1条开始，历史片段保留')
            elif action=='start' and not self.ep:self.toggle()
            elif action=='stop' and self.ep:self.toggle()
            elif action=='toggle':self.toggle()
        except (ValueError,KeyError) as e:
            self.notify('blocked','未开始采集，数据尚未就绪：'+str(e))
            print('START BLOCKED:',e,flush=True)
    def tick(self):
        now=time.monotonic_ns()
        if self.ep and now>=self.next_frame:
            try:
                if shutil.disk_usage(self.root).free<5*1024**3:raise ValueError('disk below 5GiB')
                if now-self.next_frame>2e9/self.fps:raise ValueError('recording scheduler gap')
                self.ep.append(make_frame(self.latest,now));self.next_frame+=int(1e9/self.fps)
            except (ValueError,KeyError) as e:self.fail(str(e))
    def fail(self,reason):
        self.faults[reason]+=1
        if self.ep:
            self.ep.close(reason);self.ep=None
            self.notify('fault',f'第{self.take_number}条采集中断，未保存为有效片段')
        print('CAPTURE FAULT:',reason,flush=True)
    def status(self):
        now=time.monotonic_ns()
        try:make_frame(self.latest,now);ready=True;why=None
        except (ValueError,KeyError) as e:ready=False;why=str(e)
        return {'batch_id':self.batch_id,'frames':self.ep.count if self.ep else self.last_frames,'duration_s':(now-self.record_started_ns)/1e9 if self.ep else self.last_duration_s,'source':'NVIDIA SONIC ZMQ + Dex1 hardware adapter','speech':getattr(self.announce,'last_result',None),'saved_episodes':self.saved_episodes,'take_number':self.take_number,'last_event':self.last_event,'last_saved_path':self.last_saved_path,'ready':ready,'blocked_reason':why,'counts':dict(self.counts),'faults':dict(self.faults),
                'recording':self.ep is not None,'ages_s':{k:(now-v['mono_ns'])/1e9 for k,v in self.latest.items()},
                'robot_motion_started_by_recorder':False,'strict_sensor_synchronization_verified':False}
    def close(self):
        if self.ep:
            self.ep.close('process_exit');self.ep=None
            self.notify('incomplete',f'第{self.take_number}条未正常结束，未保存为有效片段')
        (self.root/'status.json').write_text(json.dumps(self.status(),indent=2))

def subscribe_dds(events,network,routes,overflow):
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize,ChannelSubscriber
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorStates_,MotorCmds_
    ChannelFactoryInitialize(0,network);subs=[]
    def callback(key,msg,field):
        rows=getattr(msg,field)
        if not rows:return
        m=rows[0];names=('q','dq','tau_est') if field=='states' else ('q','dq','tau','kp','kd','mode')
        data={n:getattr(m,n) for n in names}
        try:events.put_nowait((key,data,None,time.monotonic_ns(),time.time_ns()))
        except queue.Full:overflow.set()
    for physical,wire in routes.items():
        for suffix,typ,field in [('state',MotorStates_,'states'),('cmd',MotorCmds_,'cmds')]:
            key=f'dex1_{physical}_{suffix}'
            s=ChannelSubscriber(f'rt/dex1/{wire}/{suffix}',typ)
            s.Init(lambda msg,k=key,f=field:callback(k,msg,f),10);subs.append(s)
    return subs

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-root',default='/opt/g1/workspace/recordings')
    p.add_argument('--camera-host',help='SONIC camera host; defaults to robot host');p.add_argument('--robot-host',default='192.168.123.164');p.add_argument('--pico-host',default='192.168.123.99')
    p.add_argument('--network',default='enp4s0');p.add_argument('--fps',type=int,default=15,choices=range(1,31))
    p.add_argument('--task',required=True);p.add_argument('--seconds',type=float,default=0)
    p.add_argument('--command-file',help='GUI atomic recording request file');p.add_argument('--probe',action='store_true',help='only observe readiness; never starts an episode')
    p.add_argument('--no-dds',action='store_true',help='camera/ZMQ diagnosis only; cannot pass readiness')
    a=p.parse_args()
    lock=(Path('/opt/g1/workspace/capture')/'recorder.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('数采已运行，请使用现有录制器，不能重复启动')
    command_id=time.time_ns()
    ctx=zmq.Context();poll=zmq.Poller();sources={};events=queue.Queue(maxsize=4096);overflow=threading.Event()
    profile=WBC/'official_sonic/profiles/dex1-routing.json'
    if not profile.exists():profile=WBC/'official_sonic/profiles/dex1-routes.json'
    # Exact established physical/wire mapping, not inferred from names.
    routes={'left':'right','right':'left'}
    candidates=list((WBC/'official_sonic/profiles').glob('*.json'))
    verified=[x for x in candidates if 'physical_to_wire' in json.loads(x.read_text())]
    if len(verified)!=1:raise RuntimeError('expected one verified Dex1 routing profile')
    route_document=json.loads(verified[0].read_text());routes=route_document['physical_to_wire']
    if set(routes)!= {'left','right'} or set(routes.values())!={'left','right'}:raise ValueError('invalid routes')
    root=Path(a.output_root)/('PROBE_' if a.probe else 'SESSION_')
    root=Path(str(root)+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    manifest={'arguments':vars(a),'physical_to_wire':routes,'route_evidence':route_document,
              'controller_startup':False,'synthetic':False,'schema':'g1-29-dex1-v1','camera_transport':'NVIDIA SONIC ImageMessageSchema port5555','camera_storage':'upstream decoded RGB normalized to JPEG','camera_timestamps':'onboard unsynchronized clock; host receipt times also preserved'}
    capture=Capture(root,a.fps,a.task,manifest)
    from capture.speech import Speaker
    capture.announce=Speaker(a.network)
    subs=[];running=True;shutdown_requested=False
    def stop(*_):
        nonlocal running,shutdown_requested
        running=False;shutdown_requested=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    try:
        for port,key in [(5555,'cameras'),(5557,'state'),(5556,'pico'),(5558,'trigger')]:
            host=(a.camera_host or a.robot_host) if key=='cameras' else a.pico_host if key in ('pico','trigger') else a.robot_host
            s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,b'');s.setsockopt(zmq.RCVHWM,100)
            s.setsockopt(zmq.LINGER,0);s.connect(f'tcp://{host}:{port}');sources[s]=key;poll.register(s,zmq.POLLIN)
        if not a.no_dds:subs=subscribe_dds(events,a.network,routes,overflow)
        print('PASSIVE CAPTURE:',root,'\ns Enter: start/save episode; q Enter: quit. Probe disables recording.',flush=True)
        start=time.monotonic();last_status=0
        while running and (not a.seconds or time.monotonic()-start<a.seconds):
            for s,_ in poll.poll(5):
                key=sources[s];raw=s.recv();now=time.monotonic_ns();epoch=time.time_ns()
                try:
                    if key=='cameras':
                        for role,jpeg,stamp in packets(raw):capture.ingest(role,{'capture_timestamp':stamp},jpeg,now,epoch)
                        continue
                    topics=(b'g1_debug',b'robot_config') if key=='state' else (b'manager_state',b'planner',b'pose',b'command',b'dex1_trigger')
                    topic=next((t for t in topics if raw.startswith(t)),None)
                    if topic is None:continue
                    data=json.loads(raw[len(topic):]) if topic==b'dex1_trigger' else (msgpack.unpackb(raw[len(topic):],raw=False) if key=='state' else unpack(raw,topic))
                    capture.ingest(topic.decode(),data,raw,now,epoch)
                    if topic==b'manager_state':
                        toggle=bool(data.get('toggle_data_collection',[False])[0])
                        if toggle and not capture.last_toggle and not a.probe:
                            capture.request('toggle')
                        capture.last_toggle=toggle
                        if bool(data.get('toggle_data_abort',[False])[0]) and capture.ep:capture.fail('operator_discard')
                except (ValueError,KeyError,TypeError) as e:capture.fail('decode '+key+': '+str(e))
            while True:
                try:args=events.get_nowait()
                except queue.Empty:break
                try:capture.ingest(*args)
                except (ValueError,TypeError) as e:capture.fail('DDS '+str(e))
            if overflow.is_set():capture.fail('DDS queue overflow');overflow.clear()
            capture.tick()
            if a.command_file and Path(a.command_file).exists():
                try:
                    request=json.loads(Path(a.command_file).read_text())
                    if request['id']>command_id:
                        command_id=request['id']
                        if not a.probe:capture.request(request['action'])
                except (OSError,ValueError,KeyError) as e:print('录制按钮请求失败:',e,flush=True)
            if sys.stdin.isatty() and select.select([sys.stdin],[],[],0)[0]:
                key=sys.stdin.readline().strip()
                if key=='q':running=False;shutdown_requested=True
                elif key=='s' and not a.probe:
                    capture.request('toggle')
            if time.monotonic()-last_status>2:
                status=capture.status();print(json.dumps(status),flush=True)
                tmp=root/'status.tmp';tmp.write_text(json.dumps(status,indent=2));tmp.replace(root/'status.json');last_status=time.monotonic()
    finally:
        interrupted_recording=capture.ep is not None
        capture.close()
        if hasattr(capture.announce,'flush'):capture.announce.flush()
        (root/'status.json').write_text(json.dumps(capture.status(),indent=2))
        for s in sources:s.close()
        ctx.term()
        for s in subs:
            if hasattr(s,'Close'):s.Close()
        outcome=shutdown_outcome(capture.status(),shutdown_requested,interrupted_recording)
        (root/'exit-summary.json').write_text(json.dumps(outcome,indent=2))
    return outcome['exit_code']

if __name__=='__main__':sys.exit(main())
