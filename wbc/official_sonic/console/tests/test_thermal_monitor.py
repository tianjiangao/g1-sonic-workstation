import importlib,importlib.util,unittest,math

class ThermalMonitorTests(unittest.TestCase):
    def monitor(self):
        self.assertIsNotNone(importlib.util.find_spec('official_sonic.thermal_monitor'))
        return importlib.import_module('official_sonic.thermal_monitor').ThermalMonitor()
    def data(self,temp=40,delta=.87):
        q=[0.]*29;target=[0.]*29;target[10]=delta;temps=[35.]*58;temps[21]=temp
        return {'body_q':q,'last_action':target,'motor_temperature':temps}
    def test_tracking_error_alone_is_not_a_heat_alarm(self):
        m=self.monitor()
        for i in range(300):s=m.update(self.data(),i*.02)
        self.assertFalse(s['alert']);self.assertLessEqual(m.history_size,300)
    def test_rising_temperature_and_static_joint_warn_before_90(self):
        m=self.monitor()
        for i in range(300):s=m.update(self.data(40+i*.04),i*.02)
        self.assertTrue(s['alert']);self.assertLess(s['ankles'][2]['peak_C'],90)
        self.assertEqual(s['ankles'][2]['index'],10)
    def test_invalid_or_missing_temperature_cannot_look_healthy(self):
        m=self.monitor()
        for value in [[],[float('nan')]*58]:
            d=self.data();d['motor_temperature']=value
            with self.assertRaises(ValueError):m.update(d,0)
