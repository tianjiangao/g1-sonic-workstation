import time, unittest
from unittest.mock import patch
from gear_sonic.utils.teleop import input_readers as r
from gear_sonic.utils.teleop.body_freshness import FreshnessConfig,read_body_snapshot

class SDK:
 def __init__(self):self.t=[1_000_000_000]*24;self.available=True
 def get_body_timestamp_ns(self):return 0
 def get_time_stamp_ns(self):raise AssertionError('head timestamp forbidden')
 def get_body_joints_timestamp(self):return self.t.copy()
 def is_body_data_available(self):return self.available
 def get_body_joints_pose(self):return [[0,0,0,0,0,0,1]]*24
 def advance(self):self.t=[t+1_000_000 for t in self.t]

class Tests(unittest.TestCase):
 def ready(self,sdk,reader):reader._poll_once();sdk.advance();reader._poll_once()
 def test_zero_overall_timestamp_uses_local_monotonic_after_all_joints_advance(self):
  sdk=SDK()
  with patch.object(r,'xrt',sdk):
   reader=r.PicoReader();start=time.monotonic();self.ready(sdk,reader);s=reader.get_latest()
   self.assertIsNotNone(s);self.assertGreaterEqual(s['timestamp_monotonic'],start)
   self.assertEqual(reader.get_timestamp_ns(),s['timestamp_ns']);self.assertEqual(s['joint_timestamps_ns'],tuple(sdk.t))
 def test_disconnect_stays_latched_after_recovery_until_explicit_rearm(self):
  sdk=SDK()
  with patch.object(r,'xrt',sdk):
   reader=r.PicoReader(freshness_config=FreshnessConfig(stale_s=.03,max_skew_s=.02));self.ready(sdk,reader)
   time.sleep(.04);self.assertIsNone(reader.get_latest());self.assertTrue(reader.disconnected)
   sdk.advance();reader._poll_once();sdk.advance();reader._poll_once()
   self.assertIsNone(reader.get_latest());self.assertTrue(reader.disconnected)
   reader.clear_disconnect();sdk.advance();reader._poll_once();self.assertIsNone(reader.get_latest())
   sdk.advance();reader._poll_once();self.assertIsNotNone(reader.get_latest())
 def test_invalid_pose_immediately_drops_cache_and_latches_fault(self):
  sdk=SDK()
  with patch.object(r,'xrt',sdk):
   reader=r.PicoReader();self.ready(sdk,reader)
   sdk.get_body_joints_pose=lambda:[[0]*7]*24;sdk.advance();reader._poll_once()
   self.assertIsNone(reader.get_latest());self.assertTrue(reader.disconnected)
 def test_unavailable_immediately_drops_cache(self):
  sdk=SDK()
  with patch.object(r,'xrt',sdk):
   reader=r.PicoReader();self.ready(sdk,reader);sdk.available=False;reader._poll_once()
   self.assertIsNone(reader.get_latest());self.assertTrue(reader.disconnected)
 def test_snapshot_retries_and_rejects_concurrent_update(self):
  sdk=SDK()
  def changing():sdk.advance();return sdk.t.copy()
  sdk.get_body_joints_timestamp=changing
  with self.assertRaisesRegex(ValueError,'unstable_snapshot'):read_body_snapshot(sdk)
 def test_publishing_fails_closed_when_sample_expired(self):
  from gear_sonic.scripts.pico_manager_thread_server import _send_fresh
  class Reader:
   def get_latest(self):return None
  class Sink:
   def send(self,m):raise AssertionError('must not send stale data')
  with self.assertRaisesRegex(RuntimeError,'refusing to publish'):_send_fresh(Sink(),b'pose',Reader())
 def test_expired_computation_is_not_allowed_by_a_newer_reader_frame(self):
  from gear_sonic.scripts.pico_manager_thread_server import _send_fresh
  class Reader:
   def get_latest(self):return {'timestamp_monotonic':time.monotonic()}
  class Sink:
   def send(self,m):raise AssertionError('must not send expired computation')
  with self.assertRaisesRegex(RuntimeError,'Computed body sample expired'):
   _send_fresh(Sink(),b'pose',Reader(),sample={'timestamp_monotonic':time.monotonic()-1})
if __name__=='__main__':unittest.main()
