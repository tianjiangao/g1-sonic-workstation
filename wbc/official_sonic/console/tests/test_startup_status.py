import importlib,importlib.util,unittest

class StartupStatusTests(unittest.TestCase):
    def get_status(self):
        self.assertIsNotNone(importlib.util.find_spec('official_sonic.startup_status'))
        return importlib.import_module('official_sonic.startup_status').StartupStatus()
    def test_initialization_is_not_idle_and_requires_actual_control_evidence(self):
        status=self.get_status();status.feed('Init Do');status.feed('ne\n')
        self.assertEqual(status.phase,'WAIT_ENABLE')
        status.feed('Replanning with mode: IDLE\n')
        self.assertEqual(status.phase,'WAIT_ENABLE')
        status.feed('[Control] DEBUG: operator_state.start=true, transitioning to CONTROL state\nReplanning with mode: IDLE\n')
        self.assertEqual(status.phase,'IDLE_REFERENCE')
        self.assertFalse(status.snapshot()['physical_motion_verified'])
    def test_heat_warning_stays_visible_after_later_idle_logs(self):
        status=self.get_status();status.feed('[HighTemp] Warning! High temperature at Right Ankle Pitch(90)\nReplanning with mode: IDLE\n')
        self.assertEqual(status.phase,'THERMAL_ALARM')
        self.assertIn('Right Ankle Pitch',status.snapshot()['alert'])
    def test_diagnostic_trend_cannot_downgrade_a_real_high_temperature_alarm(self):
        status=self.get_status();status.feed('[HighTemp] Right Ankle Pitch(90)\n')
        self.assertTrue(callable(getattr(status,'observe_thermal',None)))
        status.observe_thermal({'peak_C':89,'alert':'右踝温度趋势'})
        self.assertEqual(status.phase,'THERMAL_ALARM')
        self.assertIn('Right Ankle Pitch',status.alert)
