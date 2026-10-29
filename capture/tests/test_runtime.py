import json
from pathlib import Path
import tempfile
import time
import unittest
import cv2
import numpy as np
from capture.record import Capture,unpack
from capture.tests.test_contract import sample

class RuntimeTests(unittest.TestCase):
    def test_decoder_rejects_truncated_and_trailing_binary(self):
        header=json.dumps({'fields':[{'name':'x','dtype':'f32','shape':[1]}]}).encode().ljust(1280,b'\0')
        good=b'pose'+header+np.array([1.5],dtype='<f4').tobytes()
        self.assertEqual(unpack(good,b'pose')['x'],[1.5])
        for value in (good[:-1],good+b'\0'):
            with self.assertRaises(ValueError):unpack(value,b'pose')
    def test_camera_error_rejects_wrong_role_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'session',15,'test',{'synthetic':True})
            _,jpeg=cv2.imencode('.jpg',np.zeros((480,640,3),np.uint8))
            with self.assertRaises(ValueError):c.ingest('camera_head',None,jpeg.tobytes())
            c.close()
    def test_camera_dedup_preserves_bytes_and_all_receipt_events(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'session',15,'test',{'synthetic':True})
            c.ep=__import__('capture.core',fromlist=['Episode']).Episode(c.root/'episode')
            _,jpeg=cv2.imencode('.jpg',np.zeros((480,640,3),np.uint8));raw=jpeg.tobytes()
            c.ingest('camera_left',None,raw);c.ingest('camera_left',None,raw)
            c.close();files=list((c.root/'episode/images').glob('*.jpg'))
            self.assertEqual(len(files),1);self.assertEqual(files[0].read_bytes(),raw)
            self.assertEqual(len((c.root/'episode/events.jsonl').read_text().splitlines()),2)
    def test_capture_refuses_start_without_controller(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'session',15,'test',{'synthetic':True})
            with self.assertRaises(ValueError):c.toggle()
            self.assertEqual(list(c.root.glob('episode_*')),[]);c.close()
    def test_timeout_closes_episode_and_does_not_resume(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'session',15,'test',{'synthetic':True});now=time.monotonic_ns()
            c.latest=sample()
            for v in c.latest.values():v['mono_ns']=now
            c.ep=__import__('capture.core',fromlist=['Episode']).Episode(c.root/'episode')
            c.next_frame=now;c.latest['g1_debug']['mono_ns']=now-1_000_000_000;c.tick()
            self.assertIsNone(c.ep)
            meta=json.loads((c.root/'episode/episode.json').read_text())
            self.assertFalse(meta['complete']);self.assertIn('stale',meta['reason'])
            c.latest['g1_debug']['mono_ns']=time.monotonic_ns();c.tick();self.assertIsNone(c.ep);c.close()

if __name__=='__main__':unittest.main()
