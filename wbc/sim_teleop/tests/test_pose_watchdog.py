import unittest
from sim_teleop.telemetry import PoseWatchdog

class PoseWatchdogTests(unittest.TestCase):
 def test_reenter_pose_has_new_deadline_not_previous_pose_receipt(self):
  w=PoseWatchdog();w.mode(1,10);w.pose(10.1);w.mode(3,11)
  self.assertFalse(w.expired(30));w.mode(1,30)
  self.assertFalse(w.expired(30.1));w.pose(30.2)
  self.assertFalse(w.expired(30.6));self.assertTrue(w.expired(30.8))
 def test_entering_pose_without_any_frame_still_times_out(self):
  w=PoseWatchdog();w.mode(1,10)
  self.assertFalse(w.expired(10.4));self.assertTrue(w.expired(10.6))
 def test_repeated_mode_messages_do_not_extend_missing_frame_deadline(self):
  w=PoseWatchdog();w.mode(1,10);w.mode(1,10.4)
  self.assertTrue(w.expired(10.6))
