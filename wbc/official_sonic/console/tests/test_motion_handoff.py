import unittest
from unittest.mock import Mock
from official_sonic.motion_handoff import handoff

class HandoffTests(unittest.TestCase):
    def test_official_sdk_tuple_success_is_verified_not_misread_as_failure(self):
        c=Mock();c.CheckMode.side_effect=[(0,{'name':'ai'}),(0,{'name':''})];c.ReleaseMode.return_value=(0,None)
        self.assertTrue(handoff(c,True,pause=lambda _:None)['released'])
        c.ReleaseMode.assert_called_once()
    def test_official_sdk_tuple_error_is_not_retried(self):
        c=Mock();c.CheckMode.return_value=(0,{'name':'ai'});c.ReleaseMode.return_value=(3102,None)
        with self.assertRaisesRegex(RuntimeError,'3102'):handoff(c,True,pause=lambda _:None)
        c.ReleaseMode.assert_called_once()
    def test_inspect_never_releases(self):
        c=Mock();c.CheckMode.return_value=(0,{'name':'ai'})
        self.assertTrue(handoff(c,False)['release_required']);c.ReleaseMode.assert_not_called()
    def test_confirmed_ai_releases_then_verifies_empty_mode(self):
        c=Mock();c.CheckMode.side_effect=[(0,{'name':'ai'}),(0,{'name':''})];c.ReleaseMode.return_value=0
        self.assertTrue(handoff(c,True,pause=lambda _:None)['released']);c.ReleaseMode.assert_called_once()
    def test_unknown_mode_or_failed_query_never_releases(self):
        for response in [(3102,None),(0,{'name':'unknown'})]:
            c=Mock();c.CheckMode.return_value=response
            with self.assertRaises(RuntimeError):handoff(c,True,pause=lambda _:None)
            c.ReleaseMode.assert_not_called()
    def test_failed_release_does_not_claim_handoff(self):
        c=Mock();c.CheckMode.return_value=(0,{'name':'ai'});c.ReleaseMode.return_value=1
        with self.assertRaises(RuntimeError):handoff(c,True,pause=lambda _:None)
    def test_already_released_has_no_mode_change(self):
        c=Mock();c.CheckMode.return_value=(0,{'name':''})
        self.assertFalse(handoff(c,True)['release_required']);c.ReleaseMode.assert_not_called()

class StartupOrderTests(unittest.TestCase):
    def test_release_is_verified_before_dds_gate_and_dex1_start(self):
        from unittest.mock import patch
        from official_sonic.run_real_teleop import preflight
        from official_sonic.console.backend import Config
        events=[]
        d={'controllers':[],'autostart':'inactive','dex1_pids':[],'container_running':True}
        def remote(config,action):events.append(action);return dict(d)
        def release(**kwargs):self.assertTrue(kwargs['release']);events.append('release');return {'released':True}
        def dds(*args):events.append('verify_dds');return {'lowcmd_count':0}
        with patch('official_sonic.run_real_teleop.verify_health_hold'),patch('official_sonic.run_real_teleop.remote_action',side_effect=remote),patch('official_sonic.run_real_teleop.motion_handoff',side_effect=release),patch('official_sonic.run_real_teleop.body_dds_check',side_effect=dds):
            preflight(Config())
        self.assertEqual(events,['inspect','prepare','release','verify_dds','start-dex1'])
    def test_remaining_writer_prevents_any_further_startup(self):
        from unittest.mock import patch
        from official_sonic.run_real_teleop import preflight
        from official_sonic.console.backend import Config
        calls=[];d={'controllers':[],'autostart':'inactive','dex1_pids':[],'container_running':True}
        def remote(config,action):calls.append(action);return dict(d)
        with patch('official_sonic.run_real_teleop.verify_health_hold'),patch('official_sonic.run_real_teleop.remote_action',side_effect=remote),patch('official_sonic.run_real_teleop.motion_handoff',return_value={'released':True}),patch('official_sonic.run_real_teleop.body_dds_check',side_effect=RuntimeError('remaining LowCmd')):
            with self.assertRaisesRegex(RuntimeError,'remaining LowCmd'):preflight(Config())
        self.assertNotIn('start-dex1',calls)

class DiscoveryRetryTests(unittest.TestCase):
    def test_boot_discovery_can_recover_after_more_than_three_queries(self):
        c=Mock();c.CheckMode.side_effect=[(3102,None)]*5+[(0,{'name':''})]
        self.assertFalse(handoff(c,False,pause=lambda _:None)['release_required'])
        self.assertEqual(c.CheckMode.call_count,6);c.ReleaseMode.assert_not_called()
    def test_transient_send_failure_retries_query_only(self):
        c=Mock();c.CheckMode.side_effect=[(3102,None),(0,{'name':''})]
        self.assertFalse(handoff(c,False,pause=lambda _:None)['release_required'])
        self.assertEqual(c.CheckMode.call_count,2);c.ReleaseMode.assert_not_called()
    def test_persistent_send_failure_is_bounded_and_never_releases(self):
        c=Mock();c.CheckMode.return_value=(3102,None)
        with self.assertRaisesRegex(RuntimeError,'3102'):handoff(c,True,pause=lambda _:None)
        self.assertEqual(c.CheckMode.call_count,16);c.ReleaseMode.assert_not_called()
    def test_release_rpc_is_never_retried(self):
        c=Mock();c.CheckMode.return_value=(0,{'name':'ai'});c.ReleaseMode.return_value=3102
        with self.assertRaises(RuntimeError):handoff(c,True,pause=lambda _:None)
        c.ReleaseMode.assert_called_once()
