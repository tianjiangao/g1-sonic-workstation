"""Read-only SONIC preview to an atomic disk cache for system Tk/PIL."""
import argparse,json,time,signal
from pathlib import Path
import cv2,numpy as np,zmq
from capture.sonic_camera import packets

def main():
 p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');p.add_argument('--host',required=True);p.add_argument('--cache',required=True);p.add_argument('--seconds',type=float,default=0);a=p.parse_args()
 cache=Path(a.cache);cache.mkdir(parents=True,exist_ok=True);ctx=zmq.Context();s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,b'');s.setsockopt(zmq.CONFLATE,1);s.setsockopt(zmq.LINGER,0);s.connect('tcp://'+a.host+':5555')
 running=True
 def stop(*_):
  nonlocal running
  running=False
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 start=time.monotonic();last=0;count=0
 try:
  while running and (not a.seconds or time.monotonic()-start<a.seconds):
   if not s.poll(200):continue
   raw=s.recv();count+=1
   if time.monotonic()-last<.15:continue
   metadata={}
   for role,jpeg,stamp in packets(raw):
    im=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
    if im is None:raise ValueError('bad JPEG '+role)
    if im.shape!=((480,1280,3) if role=='camera_head' else (480,640,3)):raise ValueError('unexpected image shape '+role)
    h,w=im.shape[:2];preview_width=1280 if role=='camera_head' else 640;thumb=cv2.resize(im,(preview_width,round(preview_width*h/w)))
    ok,encoded=cv2.imencode('.jpg',thumb)
    if not ok:raise ValueError('preview encoding')
    tmp=cache/(role+'.tmp');tmp.write_bytes(encoded.tobytes());tmp.replace(cache/(role+'.jpg'))
    metadata[role]={'shape':list(im.shape),'source_timestamp':stamp,'received_at':time.time()}
   tmp=cache/'status.tmp';tmp.write_text(json.dumps({'received_at':time.time(),'frames_received':count,'average_fps':count/max(.001,time.monotonic()-start),'cameras':metadata}));tmp.replace(cache/'status.json');last=time.monotonic()
   if a.once and set(metadata)=={'camera_head','camera_left','camera_right'}:break
  if a.once and (not count or set(metadata)!={'camera_head','camera_left','camera_right'}):raise RuntimeError('No complete SONIC three-camera stream')
 finally:s.close();ctx.term()
if __name__=='__main__':main()
