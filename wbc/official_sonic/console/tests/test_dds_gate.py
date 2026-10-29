import unittest
from official_sonic.run_real_teleop import validate_dds_probe

class DdsGateTests(unittest.TestCase):
    def test_live_lowcmd_reports_conflict_with_fresh_state(self):
        with self.assertRaisesRegex(RuntimeError,'1927.*LowCmd'):
            validate_dds_probe([{'lowcmd_count':1927,'lowstate_count':2048,'state_age_s':.000221}])
    def test_missing_state_reports_state_problem(self):
        with self.assertRaisesRegex(RuntimeError,'LowState'):
            validate_dds_probe([{'lowcmd_count':0,'lowstate_count':0,'state_age_s':10}])
    def test_zero_gain_commands_are_still_a_control_conflict(self):
        with self.assertRaisesRegex(RuntimeError,'LowCmd'):
            validate_dds_probe([{'lowcmd_count':12,'lowstate_count':100,'state_age_s':.001,'kp':[0]*29,'kd':[0]*29}])
    def test_valid_idle_body_passes(self):
        validate_dds_probe([{'lowcmd_count':0,'lowstate_count':200,'state_age_s':.001,'temperature_C':[40]*58,'motor_errors':[0]*29,'state_q':[0.]*29}])
    def test_hot_or_missing_thermal_feedback_never_passes(self):
        base={'lowcmd_count':0,'lowstate_count':200,'state_age_s':.001,'temperature_C':[40]*58,'motor_errors':[0]*29,'state_q':[0.]*29}
        for override in [{'temperature_C':[]},{'temperature_C':[float('nan')]*58},{'temperature_C':[90]*58},{'motor_errors':[8]*29},{'state_age_s':float('nan')}]:
            with self.assertRaises(RuntimeError):validate_dds_probe([dict(base,**override)])
