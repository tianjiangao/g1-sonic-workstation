import unittest
from unittest.mock import Mock,patch
from official_sonic.streamer import DesktopPicoReader

class DesktopReadinessTests(unittest.TestCase):
    def test_starts_service_before_sdk_acquisition(self):
        calls=[];r=DesktopPicoReader()
        try:
            with patch('official_sonic.streamer.ensure_pc_service',side_effect=lambda:calls.append('service')),patch('sim_teleop.process_reader.ProcessPicoReader.start',side_effect=lambda:calls.append('sdk')):r.start()
            self.assertEqual(calls,['service','sdk'])
        finally:r.stop()
    def test_waits_for_headset_and_reports_no_packets_clearly(self):
        r=DesktopPicoReader()
        try:
            with patch.object(r,'get_latest',return_value=None),patch.object(r,'freshness_stats',return_value={'packets':0,'accepted_frames':0,'reason':'warming_up'}):
                with self.assertRaisesRegex(RuntimeError,'头显.*0'):r.wait_ready(timeout=.02)
        finally:r.stop()
    def test_readiness_requires_fresh_sample_and_twenty_accepted_frames(self):
        r=DesktopPicoReader()
        try:
            with patch.object(r,'get_latest',return_value={'timestamp_monotonic':0}),patch.object(r,'freshness_stats',return_value={'packets':10,'accepted_frames':19,'reason':'ready'}):
                with self.assertRaises(RuntimeError):r.wait_ready(timeout=.02)
        finally:r.stop()
    def test_fault_never_restarts_or_unlocks_reader(self):
        r=DesktopPicoReader();r.fault=True;r.latch_reason='stale_joint_content'
        try:
            with self.assertRaisesRegex(RuntimeError,'stale_joint_content'):r.wait_ready(timeout=.02)
        finally:r.stop()

class ReadyBeforeBodyTests(unittest.TestCase):
    def test_stale_or_latched_snapshot_cannot_start_body(self):
        import json,os,tempfile,time
        from pathlib import Path
        from official_sonic.run_real_teleop import pico_ready
        process=Mock();process.poll.return_value=None
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'pico.json';path.write_text(json.dumps({'reason':'ready','accepted_frames':20,'fault_latched':False}))
            self.assertTrue(pico_ready(path,process))
            os.utime(path,(time.time()-1,time.time()-1));self.assertFalse(pico_ready(path,process))
            path.write_text(json.dumps({'reason':'ready','accepted_frames':20,'fault_latched':True}));self.assertFalse(pico_ready(path,process))
            process.poll.return_value=1;self.assertFalse(pico_ready(path,process))
