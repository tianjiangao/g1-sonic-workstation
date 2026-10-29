"""Keep SDK callbacks independent of native IK/FK operations holding the GIL.

Local multiprocessing queues only; device/network payloads are never unpickled.
All processes inherit the verified simulation network namespace.
"""
import multiprocessing as mp
from queue import Empty,Full
from pathlib import Path
import threading
import time
from sim_teleop.packet_reader import AtomicPicoReader


def sdk_worker(queue,stop,output):
    reader=AtomicPicoReader(output)
    try:
        reader.start()
        while not stop.wait(.005):
            sample=reader.get_latest()
            with reader.lock:controllers=dict(reader.controllers)
            item={'sample':sample,'controllers':controllers,'stats':reader.freshness_stats()}
            try:queue.put_nowait(item)
            except Full:
                try:queue.get_nowait()
                except Empty:pass
                try:queue.put_nowait(item)
                except Full:pass
            if item['stats']['fault_latched']:break
    finally:reader.stop()


class ProcessPicoReader(AtomicPicoReader):
    def __init__(self,output=None,worker=sdk_worker):
        self.output=output;self.worker=worker;self.freshness_stale_s=.25
        self.context=mp.get_context('spawn');self.queue=self.context.Queue(maxsize=2)
        self.stop_event=self.context.Event();self.lock=threading.Lock();self.controllers={};self.sdk=self
        self.fault=False;self.latch_reason=None;self.item=None;self.process=None;self.ever_ready=False
    def start(self):
        if self.process is not None:raise RuntimeError('SDK reader already started')
        self.process=self.context.Process(target=self.worker,args=(self.queue,self.stop_event,self.output),daemon=True)
        self.process.start()
    def _drain(self):
        if self.process is not None and not self.process.is_alive():
            self.fault=True;self.latch_reason=self.latch_reason or 'acquisition_process_exited'
            return
        while True:
            try:self.item=self.queue.get_nowait()
            except Empty:break
        if self.item:
            self.controllers=self.item['controllers']
            stats=self.item['stats'];sample=self.item['sample']
            if stats.get('fault_latched'):
                self.fault=True;self.latch_reason=self.latch_reason or stats.get('latch_reason',stats.get('reason'))
            if sample is not None:
                self.ever_ready=True
                if time.monotonic()-sample['timestamp_monotonic']>=self.freshness_stale_s:
                    self.fault=True;self.latch_reason=self.latch_reason or 'stale_acquisition_process_frame'
        if self.process is not None and not self.process.is_alive():
            self.fault=True;self.latch_reason=self.latch_reason or 'acquisition_process_exited'
    def get_latest(self):
        self._drain()
        return self.item['sample'] if self.item and not self.fault else None
    @property
    def disconnected(self):
        self._drain();return self.fault
    def freshness_stats(self):
        self._drain()
        return dict(self.item['stats'] if self.item else {'reason':'warming_up','accepted_frames':0},
                    fault_latched=self.fault,latch_reason=self.latch_reason,
                    acquisition_pid=self.process.pid if self.process else None)
    def wait_ready(self,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if self.disconnected:raise RuntimeError('PICO fault: '+str(self.latch_reason))
            if self.get_latest() is not None and self.freshness_stats()['accepted_frames']>=20:return
            time.sleep(.01)
        raise RuntimeError('PICO not ready: '+self.freshness_stats()['reason'])
    def stop(self):
        if self.process and self.process.is_alive():self.stop_event.set()
        if self.process:
            self.process.join(timeout=3)
            if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
            if self.process.is_alive():self.process.kill();self.process.join()
        self.queue.close();self.queue.cancel_join_thread()
