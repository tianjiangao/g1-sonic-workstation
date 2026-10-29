import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import importlib.util
SPEC = importlib.util.find_spec("official_sonic.console.ssh_connection")
if SPEC:
    from official_sonic.console import ssh_connection as ssh

class SshModuleTests(unittest.TestCase):
    def test_automatic_ssh_module_exists(self):
        self.assertIsNotNone(SPEC, "Automatic SSH module is missing")

@unittest.skipUnless(SPEC, "SSH module not implemented yet")
class SshConnectionTests(unittest.TestCase):
    def test_boot_refusal_recovers_in_one_wait_but_auth_is_not_retried(self):
        self.assertTrue(callable(getattr(ssh,'wait_for_connection',None)))
        replies=[Mock(returncode=255,stdout='',stderr='Connection refused'),Mock(returncode=0,stdout='unitree-g1-nx\n',stderr='')]
        with patch.object(ssh.subprocess,'run',side_effect=replies) as run:
            self.assertEqual(ssh.wait_for_connection('192.168.123.164',pause=lambda _:None)['hostname'],'unitree-g1-nx')
            self.assertEqual(run.call_count,2)
        with patch.object(ssh.subprocess,'run',return_value=Mock(returncode=255,stdout='',stderr='Permission denied')) as run:
            with self.assertRaisesRegex(RuntimeError,'Permission denied'):ssh.wait_for_connection('192.168.123.164',pause=lambda _:None)
            self.assertEqual(run.call_count,1)
    def test_boot_wait_has_a_deadline_and_never_accepts_wrong_identity(self):
        self.assertTrue(callable(getattr(ssh,'wait_for_connection',None)))
        ticks=[0.]
        def pause(s):ticks[0]+=s
        with patch.object(ssh.subprocess,'run',return_value=Mock(returncode=255,stdout='',stderr='Connection refused')) as run:
            with self.assertRaisesRegex(RuntimeError,'就绪超时'):ssh.wait_for_connection('192.168.123.164',timeout=2,pause=pause,clock=lambda:ticks[0])
            self.assertLessEqual(run.call_count,3)
        with patch.object(ssh.subprocess,'run',return_value=Mock(returncode=0,stdout='wrong-host\n',stderr='')) as run:
            with self.assertRaisesRegex(RuntimeError,'身份'):ssh.wait_for_connection('192.168.123.164',pause=lambda _:None)
            self.assertEqual(run.call_count,1)
    def test_automatic_connection_is_pinned_noninteractive_and_bounded(self):
        args = ssh.ssh_args('192.168.123.164')
        for value in ('ControlMaster=auto', 'ControlPersist=30m', 'BatchMode=yes',
                      'StrictHostKeyChecking=yes', 'IdentitiesOnly=yes', 'ConnectTimeout=5',
                      'ServerAliveInterval=5', 'ServerAliveCountMax=2', 'ForwardAgent=no',
                      'ClearAllForwardings=yes'):
            self.assertIn(value, args)
        self.assertEqual(args[-1], 'unitree@192.168.123.164')
        self.assertIn(str(ssh.IDENTITY), args)
        self.assertEqual(args[args.index('-S')+1], str(Path.home()/'.cache/g1-real-teleop/control'))
    def test_other_hosts_never_receive_g1_identity_or_share_its_socket(self):
        args = ssh.ssh_args('192.168.123.165')
        self.assertNotIn(str(ssh.IDENTITY), args)
        self.assertNotEqual(args[args.index('-S')+1], str(Path.home()/'.cache/g1-real-teleop/control'))
    def test_invalid_host_is_rejected_before_subprocess(self):
        for host in ('-oProxyCommand=bad', '192.168.123.164; echo bad', 'example.com'):
            with self.assertRaises(ValueError): ssh.ssh_args(host)
    def test_probe_only_runs_hostname_and_checks_real_identity(self):
        with patch.object(ssh.subprocess, 'run', return_value=Mock(returncode=0, stdout='unitree-g1-nx\n', stderr='')) as run:
            result = ssh.connect('192.168.123.164')
        self.assertEqual(result['hostname'], 'unitree-g1-nx')
        self.assertEqual(run.call_args.args[0][-1], 'hostname')
        self.assertEqual(run.call_args.kwargs['timeout'], 12)
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
    def test_failed_auth_timeout_and_wrong_machine_are_not_success(self):
        with patch.object(ssh.subprocess, 'run', return_value=Mock(returncode=255, stdout='', stderr='Permission denied')):
            with self.assertRaisesRegex(RuntimeError, 'Permission denied'): ssh.connect('192.168.123.164')
        with patch.object(ssh.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['ssh'],12)):
            with self.assertRaisesRegex(RuntimeError, '超时'): ssh.connect('192.168.123.164')
        with patch.object(ssh.subprocess, 'run', return_value=Mock(returncode=0, stdout='wrong-robot\n', stderr='')):
            with self.assertRaisesRegex(RuntimeError, '身份'): ssh.connect('192.168.123.164')
    def test_robot_and_camera_actions_share_automatic_connection(self):
        from official_sonic.run_real_teleop import ssh_args
        from official_sonic.console.backend import Config
        self.assertIn('ControlMaster=auto', ssh_args(Config()))
        for name in ('ensure_camera.py', 'remote_inventory.py', 'camera_preview.py'):
            source = (Path(ssh.__file__).parent/name).read_text()
            self.assertIn('ssh_args(', source)
            self.assertNotIn("['ssh'", source)
    def test_gui_connects_at_start_and_processes_connectivity_events(self):
        source = (Path(ssh.__file__).parent/'app.py').read_text()
        self.assertIn('self.check_ssh()', source)
        self.assertIn("kind=='ssh'", source)
        self.assertIn('30000,self.check_ssh', source)

if __name__ == '__main__': unittest.main()
