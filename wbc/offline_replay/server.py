"""Independent passive replay server. Loopback HTTP only; finite request queue."""
import os
os.environ.setdefault('MUJOCO_GL','egl')
os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE','1')
os.environ.setdefault('__EGL_VENDOR_LIBRARY_FILENAMES','/usr/share/glvnd/egl_vendor.d/50_mesa.json')
import argparse,base64,json,signal,time,sys
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import cv2
from offline_replay.core import Episode,BodyModel,NAMES,fingerprints

class Server(HTTPServer):request_queue_size=1

def main():
    p=argparse.ArgumentParser();p.add_argument('--episode',required=True);p.add_argument('--port',type=int,default=0);p.add_argument('--receipt',required=True)
    a=p.parse_args()
    if a.port in (5555,5556,5557) or not 0<=a.port<=65535:raise ValueError('Reserved or invalid port')
    out=Path(a.receipt)
    if out.exists():raise FileExistsError('Refusing to overwrite replay receipt')
    out.parent.mkdir(parents=True,exist_ok=True);os.nice(10)
    episode=Episode(a.episode);before=fingerprints(episode.path);model=BodyModel();model.render(episode.frames[0]['q'],dex1=episode.frames[0]['dex1_state'])
    start=time.time();rendered=0;render_seconds=0.
    meta={'kind':episode.kind,'task':episode.task,'frames':len(episode.frames),'duration':episode.duration,'times':episode.times,'joints':NAMES,
        'actual':[f['q'] for f in episode.frames],'target':[f['target'] for f in episode.frames],
        'dex_state':[f['dex1_state'] for f in episode.frames],'dex_command':[f['dex1_command'] for f in episode.frames],
        'model':'G1 29 body + Dex1 4 visual slides; raw gripper data remains 2D radians',
        'root':'FIXED BASE · no verified global translation/orientation','units':'rad','mujoco_actuators':model.model.nu,
        'body_qpos_addresses':model.addresses,'finger_qpos_addresses':model.finger_addresses,
        'forbidden_imports_loaded':[k for k in sys.modules if k.startswith(('unitree_sdk2py','zmq','gear_sonic','sim_teleop'))],
        'data_sources':{'actual':'observation.body = original g1_debug.body_q / body_q_measured',
            'target':'action.body = g1_debug.last_action, already scaled/offset radians; not measured feedback',
            'human':'PICO/SMPL human poses are NOT robot joint angles', 'token':'64D SONIC latent tokens are NOT joint angles'},
        'camera_streams':'3 recorded streams; head stereo split into 2 optical views (4 panes total)',
        'timeline':'Shared recorded host monotonic frame grid; sensor exposure synchronization unverified',
        'provenance_matches':episode.provenance_matches,'renderer':model.gl_renderer}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,body,ctype='application/json',status=200):
            if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            nonlocal rendered,render_seconds
            u=urlsplit(self.path);query=parse_qs(u.query)
            try:
                if u.path=='/':return self.reply((Path(__file__).parent/'viewer.html').read_bytes(),'text/html; charset=utf-8')
                if u.path=='/meta':return self.reply(meta)
                if u.path not in ('/frame','/image'):return self.reply({'error':'not found'},status=404)
                i=int(query.get('i',['0'])[0])
                if not 0<=i<len(episode.frames):raise ValueError('Invalid frame index')
                if u.path=='/image':return self.reply(episode.image(i,query.get('role',['ego_view'])[0]),'image/jpeg')
                mode=query.get('source',['actual'])[0]
                if mode not in ('actual','target'):raise ValueError('Invalid source')
                q=episode.frames[i]['q' if mode=='actual' else 'target']
                if q is None:raise ValueError('Target source unavailable; no substitution')
                az=float(query.get('az',['135'])[0]);el=float(query.get('el',['-15'])[0]);distance=float(query.get('distance',['2.5'])[0])
                if not -720<=az<=720 or not -85<=el<=85 or not .5<=distance<=6:raise ValueError('Invalid display camera')
                dex=episode.frames[i]['dex1_state' if mode=='actual' else 'dex1_command']
                if dex is None:raise ValueError('Dex1 source missing; no fabricated finger motion')
                t=time.perf_counter();rgb=model.render(q,az,el,distance,dex1=dex,gripper_source='feedback' if mode=='actual' else 'command',view=query.get('view',['body'])[0]);ok,jpg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,85])
                if not ok:raise ValueError('Render encoding failed')
                rendered+=1;render_seconds+=time.perf_counter()-t
                return self.reply({'index':i,'time_s':episode.times[i],'source':mode,'render':'data:image/jpeg;base64,'+base64.b64encode(jpg).decode(),
                    'qpos':model.data.qpos.tolist(),'q':q,'actual':episode.frames[i]['q'],'target':episode.frames[i]['target'],
                    'dex_state':episode.frames[i]['dex1_state'],'dex_command':episode.frames[i]['dex1_command'],'actuators':model.model.nu,'physics_time':float(model.data.time),'gripper_mapping':model.last_gripper})
            except (ValueError,KeyError,TypeError) as e:return self.reply({'error':str(e)},status=400)
    http=Server(('127.0.0.1',a.port),Handler);http.timeout=.3;running=True
    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    ready={'url':f'http://127.0.0.1:{http.server_port}/','pid':os.getpid(),'kind':episode.kind,'frames':len(episode.frames),'renderer':model.gl_renderer,'control_started':False}
    out.write_text(json.dumps(ready,ensure_ascii=False,indent=2));print(json.dumps(ready),flush=True)
    try:
        while running:http.handle_request()
    finally:
        http.server_close();model.close();after=fingerprints(episode.path)
        receipt=dict(ready,raw_hashes_before=before,raw_hashes_after=after,raw_unchanged=before==after,
            rendered_frames=rendered,render_seconds=render_seconds,uptime_s=time.time()-start,mujoco_steps=0,actuators=model.model.nu)
        out.with_suffix('.final.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
        if before!=after:raise RuntimeError('Raw episode files changed during replay')
if __name__=='__main__':main()
