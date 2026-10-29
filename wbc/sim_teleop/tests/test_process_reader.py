import ctypes
import multiprocessing as mp
import time
import unittest
from sim_teleop.process_reader import ProcessPicoReader


def fake_sdk(queue,stop,output):
    index=0
    while not stop.wait(.01):
        index+=1
        item={'sample':{'timestamp_monotonic':time.monotonic(),'timestamp_ns':time.monotonic_ns()},
              'controllers':{},'stats':{'accepted_frames':index,'fault_latched':False,'reason':'ready'}}
        if queue.full():
            try:queue.get_nowait()
            except Exception:pass
        try:queue.put_nowait(item)
        except Exception:pass

class ProcessReaderTests(unittest.TestCase):
    def test_native_gil_block_does_not_stop_acquisition(self):
        r=ProcessPicoReader(worker=fake_sdk)
        try:
            r.start();r.wait_ready(timeout=5)
            ctypes.PyDLL(None).usleep(400000)
            self.assertIsNotNone(r.get_latest())
            self.assertFalse(r.disconnected)
            self.assertGreater(r.freshness_stats()['accepted_frames'],30)
        finally:r.stop()
        self.assertFalse(r.process.is_alive())
    def test_worker_death_fails_closed(self):
        r=ProcessPicoReader(worker=fake_sdk)
        try:
            r.start();r.wait_ready(timeout=5);r.process.terminate();r.process.join()
            self.assertTrue(r.disconnected);self.assertIsNone(r.get_latest())
        finally:r.stop()

if __name__=='__main__':unittest.main()
