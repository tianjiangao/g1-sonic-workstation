import unittest
from official_sonic import run_real_teleop as entry

class StartupDependencyTests(unittest.TestCase):
    def test_missing_gripper_is_a_prepare_action_not_assertion(self):
        plan=entry.startup_actions({'controllers':[],'autostart':'inactive','dex1_pids':[],'container_running':False})
        self.assertEqual(plan,['prepare_container','start_dex1'])
    def test_reuses_running_dependencies(self):
        self.assertEqual(entry.startup_actions({'controllers':[],'autostart':'inactive','dex1_pids':[1],'container_running':True}),[])
    def test_refuses_duplicate_controller_and_duplicate_grippers(self):
        for field,value in [('controllers',[1]),('dex1_pids',[1,2]),('autostart','active')]:
            d={'controllers':[],'autostart':'inactive','dex1_pids':[],'container_running':True};d[field]=value
            with self.assertRaises(RuntimeError):entry.startup_actions(d)
    def test_capture_arguments_use_saved_settings_and_do_not_start_control(self):
        from official_sonic.console.backend import Config,capture_command
        c=Config(task='杯子采集',output='/tmp/capture-check',frequency=15)
        args=capture_command(c)
        self.assertIn('--command-file',args);self.assertIn('/tmp/capture-check/g1_demo',args)
        self.assertNotIn('run_real_teleop',str(args))

if __name__=='__main__':unittest.main()
