"""G1 built-in speaker only. Asynchronous official voice RPC; no motor commands."""
import argparse
import json
import queue
import threading
import time

def send_robot_speech(client,text):
    # Pinned G1 SDK doubles its index instead of incrementing from zero.
    # Seed each request with a fresh nonzero value; preserve the SDK source.
    client.tts_index=time.monotonic_ns()%1_000_000_000+1
    code=client.TtsMaker(text,0)
    if code!=0:raise RuntimeError('G1 TtsMaker RPC failed: '+str(code))
    return {'rpc_accepted':True,'audible_verified':False,'text':text,'target':'robot_speaker'}

class Speaker:
    def __init__(self,network='enp4s0'):
        self.queue=queue.Queue(maxsize=16);self.network=network;self.last_result=None
        threading.Thread(target=self._work,daemon=True).start()
    def __call__(self,text):
        print('机器人播报请求：'+text,flush=True)
        try:self.queue.put_nowait(text)
        except queue.Full:
            self.last_result={'rpc_accepted':False,'reason':'speech queue full'}
            print('语音队列已满；请看界面状态',flush=True)
    def flush(self,timeout=12):
        deadline=time.monotonic()+timeout
        while self.queue.unfinished_tasks and time.monotonic()<deadline:time.sleep(.05)
        return not self.queue.unfinished_tasks
    def _work(self):
        client=None
        while True:
            text=self.queue.get()
            try:
                import subprocess
                from pathlib import Path
                env_python='/opt/g1/audio-env/bin/python'
                command=[env_python,'-m','capture.robot_audio','--network',self.network,'--text',text]
                r=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,timeout=35)
                if r.returncode:raise RuntimeError(r.stderr[-1500:] or r.stdout[-1500:])
                lines=[line for line in r.stdout.splitlines() if line.startswith('{')]
                if not lines:raise RuntimeError('robot audio helper returned no result')
                self.last_result=json.loads(lines[-1])
                print('机器人语音RPC已接受（实际可听需现场确认）',flush=True)
            except Exception as e:
                self.last_result={'rpc_accepted':False,'reason':str(e),'text':text}
                print('机器人语音失败：'+str(e),flush=True)
            finally:self.queue.task_done()

def main():
    p=argparse.ArgumentParser();p.add_argument('--text',required=True);p.add_argument('--network',default='enp4s0');a=p.parse_args()
    s=Speaker(a.network);s(a.text);s.queue.join();print(json.dumps(s.last_result,ensure_ascii=False))

if __name__=='__main__':main()
