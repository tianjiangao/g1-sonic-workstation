"""Official SONIC manager, with the already simulation-tested SDK reader.

No command rewriting, mode changes, Unitree DDS, or controller implementation.
The reader is the existing compatibility layer for this PICO packet format.
"""
import argparse
import json
from pathlib import Path
import signal
import time
from official_sonic.console.backend import ConfigStore,ROOT
from sim_teleop.process_reader import ProcessPicoReader
from gear_sonic.utils.teleop.xrt_runtime import ensure_pc_service

class DesktopPicoReader(ProcessPicoReader):
    def start(self):
        ensure_pc_service()
        super().start()
    def wait_ready(self,timeout=60):
        deadline=time.monotonic()+timeout;last_log=-1e9
        while time.monotonic()<deadline:
            if self.disconnected:raise RuntimeError('PICO输入故障：'+str(self.latch_reason))
            sample=self.get_latest();stats=self.freshness_stats()
            if sample is not None and stats.get('accepted_frames',0)>=20:
                print('PICO就绪：真实有效全身帧不少于20帧；开始后仍执行原新鲜度保护',flush=True);return
            if time.monotonic()-last_log>=2:
                print(f"等待头显数据：packets={stats.get('packets',0)} accepted={stats.get('accepted_frames',0)} reason={stats.get('reason')}；请保持XRoboToolkit前台、Full Body/Send开启",flush=True)
                last_log=time.monotonic()
            time.sleep(.01)
        stats=self.freshness_stats()
        if not stats.get('packets',0):raise RuntimeError('头显数据包为0：PC Service可达但未收到头显全身发送；检查XRoboToolkit前台、Full Body/Send及头显网络。身体未启动。')
        raise RuntimeError(f"PICO全身数据尚未就绪：{stats.get('reason')}；accepted={stats.get('accepted_frames',0)}，没有放宽新鲜度检查。")

class Dex1InputReader(DesktopPicoReader):
    def __init__(self,output,publisher):
        super().__init__(output);self.publisher=publisher;self.trigger_sequence=0;self.last_trigger_at=None
    def get_latest(self):
        sample=super().get_latest()
        if sample is not None and sample['timestamp_monotonic']!=self.last_trigger_at:
            controllers=sample.get('pico_controllers',{})
            left=controllers.get('left',{}).get('trigger');right=controllers.get('right',{}).get('trigger')
            from official_sonic.dex1_mapping import map_triggers
            try:map_triggers(left,right)
            except ValueError:
                # Do not turn a hand-only fault into loss of valid body tracking.
                # No hand frame is emitted, so Dex1's independent freshness gate
                # stops its output while the official body manager continues.
                if not self.__dict__.get('invalid_trigger',False):
                    print(f'Dex1 trigger unavailable: left={left!r}, right={right!r}; body tracking continues',flush=True)
                self.invalid_trigger=True
                return sample
            if self.__dict__.get('invalid_trigger',False):
                print('Dex1 trigger data valid again; a stopped gripper bridge requires explicit restart',flush=True)
            self.invalid_trigger=False
            self.trigger_sequence+=1;self.last_trigger_at=sample['timestamp_monotonic']
            data={'sequence':self.trigger_sequence,'timestamp_monotonic':sample['timestamp_monotonic'],
                  'left':left,'right':right}
            self.publisher.send(b'dex1_trigger'+json.dumps(data).encode())
        return sample

def main():
    p=argparse.ArgumentParser();p.add_argument('--enable-real-zmq',action='store_true');p.add_argument('--output',required=True)
    p.add_argument('--dex1-input',action='store_true',help='publish raw fresh triggers locally; does not send motor commands')
    a=p.parse_args()
    if not a.enable_real_zmq:p.error('向真机发布必须显式指定 --enable-real-zmq')
    config=ConfigStore().load();path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    ctx=None;publisher=None
    if a.dex1_input:
        import zmq
        ctx=zmq.Context();publisher=ctx.socket(zmq.PUB);publisher.setsockopt(zmq.SNDHWM,2);publisher.bind('tcp://127.0.0.1:5558')
    reader=Dex1InputReader(path,publisher) if publisher is not None else DesktopPicoReader(path)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        from gear_sonic.scripts.pico_manager_thread_server import run_pico_manager
        print('OFFICIAL_MANAGER: unchanged PLANNER/POSE/start/stop; existing atomic SDK reader',flush=True)
        run_pico_manager(port=5556,bind_host=config.streamer_ip,zmq_feedback_host=config.robot_ip,
                         zmq_feedback_port=5557,reader=reader)
    finally:
        path.with_suffix('.final.json').write_text(json.dumps(reader.freshness_stats(),indent=2));reader.stop()
        if publisher is not None:publisher.close(linger=0);ctx.term()

if __name__=='__main__':
    try:main()
    except RuntimeError as e:print('PICO启动未完成：'+str(e),flush=True);raise SystemExit(2)
