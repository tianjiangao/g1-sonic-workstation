import unittest
from official_sonic.console.camera_preview import camera_args,check_viewer_exit

class CameraLaunchTests(unittest.TestCase):
    def test_viewer_crash_is_failure_not_success(self):
        with self.assertRaises(RuntimeError):check_viewer_exit(1)
        self.assertIsNone(check_viewer_exit(0))
        self.assertIsNone(check_viewer_exit(None))
    def test_requires_confirmed_distinct_wrist_serials(self):
        for roles in [{},{'left_wrist':{'serial':'a','confirmed':True},'right_wrist':{'serial':'a','confirmed':True}}]:
            with self.assertRaises(ValueError):camera_args(roles)
    def test_known_wrist_only_does_not_invent_head(self):
        roles={'left_wrist':{'serial':'1015','confirmed':True},'right_wrist':{'serial':'3720','confirmed':True},'ego_view':{'serial':None,'confirmed':False}}
        a=camera_args(roles)
        self.assertIn('1015',a);self.assertIn('3720',a)
        self.assertEqual(a[a.index('--ego-view-camera')+1],'None')
        self.assertEqual(a[a.index('--fps')+1],'15')

if __name__=='__main__':unittest.main()
