import unittest
from official_sonic.console.hardware import summarize,validate_roles

class HardwareTests(unittest.TestCase):
    def test_two_detected_cameras_do_not_claim_role_or_head_ready(self):
        s=summarize({'camera_devices':[{'serial':'a'},{'serial':'b'}],
                     'controllers':[],'unitree_sonic':{'ActiveState':'failed'},'dex1_units':[]})
        self.assertEqual(s['camera_devices'],2)
        self.assertFalse(s['ready_for_real_control'])
        self.assertIn('相机角色未确认',s['blockers'])
        self.assertIn('Dex1 服务未确认',s['blockers'])
    def test_missing_sdk_or_inventory_fails_explicitly(self):
        s=summarize({'camera_error':'ImportError','controllers':[]})
        self.assertIn('ImportError',s['camera_status'])
        self.assertFalse(s['ready_for_real_control'])
    def test_old_controller_and_enabled_autostart_are_visible(self):
        s=summarize({'camera_devices':[],'controllers':[{'pid':12,'exe':'g1_deploy_onnx_ref'}],
            'unitree_sonic':{'ActiveState':'active','UnitFileState':'enabled'}})
        self.assertEqual(s['controller_count'],1)
        self.assertIn('enabled',s['autostart'])
        self.assertIn('已有控制器运行',s['blockers'])
    def test_roles_require_distinct_existing_serials_and_all_views(self):
        self.assertFalse(validate_roles({'left_wrist':'a','right_wrist':'a'},['a']))
        self.assertFalse(validate_roles({'left_wrist':'a','right_wrist':'b'},['a','b']))
        self.assertFalse(validate_roles({'ego_view':'c','left_wrist':'a','right_wrist':'b'},['a','b']))
        self.assertTrue(validate_roles({'ego_view':'c','left_wrist':'a','right_wrist':'b'},['a','b','c']))

if __name__=='__main__':unittest.main()
