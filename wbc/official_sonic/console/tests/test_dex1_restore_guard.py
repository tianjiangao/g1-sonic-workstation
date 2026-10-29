import unittest
from unittest.mock import patch
from official_sonic.console import remote_prepare as remote

class RestoreGuardTests(unittest.TestCase):
    def test_running_body_prevents_service_stop(self):
        d={'controllers':[12],'autostart':'inactive','dex1_pids':[34]}
        with patch.object(remote,'inspect',return_value=d),patch.object(remote,'run') as run:
            with self.assertRaises(RuntimeError):remote.restore_dex1()
            run.assert_not_called()
    def test_wrong_executable_is_never_stopped(self):
        d={'controllers':[],'autostart':'inactive','dex1_pids':[34]}
        with patch.object(remote,'inspect',return_value=d),patch.object(remote,'run',return_value='/tmp/other-service') as run:
            with self.assertRaises(RuntimeError):remote.restore_dex1()
            self.assertEqual(run.call_count,1)
            self.assertNotIn('kill',str(run.call_args))
    def test_duplicate_services_are_not_arbitrarily_killed(self):
        d={'controllers':[],'autostart':'inactive','dex1_pids':[34,35]}
        with patch.object(remote,'inspect',return_value=d),patch.object(remote,'run') as run:
            with self.assertRaises(RuntimeError):remote.restore_dex1()
            run.assert_not_called()
