import unittest
from gear_sonic.utils.teleop.body_freshness import BodyFreshnessGate, FreshnessConfig

def pose(): return [[0.,0.,0.,0.,0.,0.,1.] for _ in range(24)]
def stamps(n): return [1_000_000_000+n*10_000_000]*24
class Tests(unittest.TestCase):
 def gate(self):return BodyFreshnessGate(FreshnessConfig(stale_s=.1,max_skew_s=.05))
 def ready(self,g):g.update(pose(),stamps(0),now=0);return g.update(pose(),stamps(1),now=.01)
 def test_normal_joint_updates_with_no_overall_timestamp(self):
  g=self.gate();s=self.ready(g);self.assertIsNotNone(s);self.assertEqual(s['joint_timestamps_ns'],tuple(stamps(1)));self.assertEqual(s['timestamp_ns'],10_000_000)
 def test_no_single_head_joint_fallback(self):
  g=self.gate()
  for n in range(3):
   t=[0]*24;t[15]=stamps(n)[15];self.assertIsNone(g.update(pose(),t,now=.01*n))
  self.assertEqual(g.stats()['joint_change_counts'][15],2);self.assertIn('missing_joint_timestamps',g.reason)
 def test_partial_freeze_blocks_new_pose_then_expires_cache(self):
  g=self.gate();s=self.ready(g);t=stamps(2);t[7]=stamps(1)[7]
  self.assertIsNone(g.update(pose(),t,now=.03));self.assertIs(g.latest(now=.04),s)
  self.assertIsNone(g.latest(now=.12));self.assertIn('stale',g.reason)
 def test_all_freeze_cannot_refresh_receipt_clock(self):
  g=self.gate();self.ready(g)
  for n in range(2,12):self.assertIsNone(g.update(pose(),stamps(1),now=.01*n))
  self.assertIsNone(g.latest(now=.12))
 def test_unavailable_invalidates_immediately_and_recovery_needs_two_frames(self):
  g=self.gate();self.ready(g);self.assertIsNone(g.update(None,None,available=False,now=.02));self.assertIsNone(g.latest(now=.02))
  self.assertIsNone(g.update(pose(),stamps(3),now=.03));self.assertIsNotNone(g.update(pose(),stamps(4),now=.04))
 def test_backwards_any_joint_invalidates(self):
  g=self.gate();self.ready(g);t=stamps(2);t[21]=stamps(0)[21]
  self.assertIsNone(g.update(pose(),t,now=.02));self.assertIsNone(g.latest(now=.02));self.assertIn('backward',g.reason)
 def test_timestamp_shape_type_and_nonpositive(self):
  for t in [stamps(0)[:23],[[1]]*24,[float('nan')]*24,[float('inf')]*24,[True]*24,[0]*24,[-1]*24,[1.5]*24]:
   g=self.gate();self.ready(g);self.assertIsNone(g.update(pose(),t,now=.02));self.assertIsNone(g.latest(now=.02))
 def test_joint_skew_rejected(self):
  g=self.gate();self.ready(g);t=stamps(2);t[8]+=100_000_000
  self.assertIsNone(g.update(pose(),t,now=.02));self.assertIn('skew',g.reason)
 def test_nan_inf_zero_and_bad_norm_quaternions(self):
  for value in [float('nan'),float('inf'),0.,2.]:
   g=self.gate();self.ready(g);p=pose();p[7][6]=value
   self.assertIsNone(g.update(p,stamps(2),now=.02));self.assertIsNone(g.latest(now=.02))
 def test_monotonic_receipt_age_independent_of_device_epoch(self):
  g=self.gate();self.ready(g);self.assertIsNotNone(g.latest(now=.05));self.assertIsNone(g.latest(now=.2))
 def test_recovery_from_freeze_requires_new_all_joint_frame(self):
  g=self.gate();self.ready(g);g.latest(now=.2)
  self.assertIsNone(g.update(pose(),stamps(1),now=.21));self.assertIsNone(g.update(pose(),stamps(2),now=.22));self.assertIsNotNone(g.update(pose(),stamps(3),now=.23))
 def test_unstable_snapshot_invalidates(self):
  g=self.gate();self.ready(g);g.invalidate('unstable_snapshot',now=.02);self.assertIsNone(g.latest(now=.02))
if __name__=='__main__':unittest.main()
