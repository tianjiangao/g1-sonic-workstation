import unittest
from offline_replay import gripper
class GripperTests(unittest.TestCase):
    def test_open_close_and_direction_use_named_slides_and_keep_raw_radians(self):
        a=gripper.GripperStateAdapter();raw={'left':0.,'right':5.4};r=a.map(raw,source='feedback')
        self.assertEqual(raw,{'left':0.,'right':5.4});self.assertEqual(r['source'],'feedback')
        self.assertEqual(r['joints']['left_dex1_finger_joint_1'],-.02)
        self.assertEqual(r['joints']['right_dex1_finger_joint_2'],.0245)
        self.assertEqual(len(r['raw_motor_rad']),2);self.assertEqual(len(r['joints']),4)
    def test_each_side_is_independent_and_midpoint_is_linear(self):
        a=gripper.GripperStateAdapter();r=a.map({'left':2.7,'right':0},source='command')
        self.assertAlmostEqual(r['joints']['left_dex1_finger_joint_1'],.00225)
        self.assertEqual(r['joints']['right_dex1_finger_joint_1'],-.02)
    def test_bad_units_unbounded_values_or_ambiguous_source_fail(self):
        a=gripper.GripperStateAdapter()
        for v in (float('nan'),90.,None):
            with self.assertRaises(ValueError):a.map({'left':v,'right':0},source='feedback')
        with self.assertRaises(ValueError):a.map({'left':0,'right':0},source='unknown')
    def test_small_encoder_overshoot_is_only_display_clipped_and_disclosed(self):
        a=gripper.GripperStateAdapter();r=a.map({'left':-.02,'right':5.41},source='feedback')
        self.assertEqual(r['raw_motor_rad']['left'],-.02);self.assertEqual(set(r['display_clipped']),{'left','right'})
