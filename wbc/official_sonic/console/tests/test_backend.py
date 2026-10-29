import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from official_sonic.console.backend import Config, ConfigStore, JobManager, real_command

class ConfigTests(unittest.TestCase):
    def test_round_trip_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            s=ConfigStore(Path(d)/'settings.json');s.save(Config())
            first=s.path.read_bytes();c=s.load();c.task='收纳杯子';s.save(c)
            self.assertEqual(s.load().task,'收纳杯子')
            self.assertEqual(list(Path(d).glob('settings.*.bak'))[0].read_bytes(),first)
    def test_invalid_persisted_json_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            s=ConfigStore(Path(d)/'settings.json');s.path.write_text('{bad')
            with self.assertRaises(ValueError):s.load()
            self.assertEqual(s.path.read_text(),'{bad')
    def test_unsafe_official_shell_launcher_values_rejected(self):
        for key,value in [('task',"cup'; touch /tmp/should-not-exist"),('dataset','../../x'),('robot_ip','x;true'),('frequency',0)]:
            c=Config();setattr(c,key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):c.validate()
    def test_no_editable_settings_unlock_real_control(self):
        with self.assertRaises(RuntimeError):real_command(Config())

class JobTests(unittest.TestCase):
    def test_refuse_unknown_job(self):
        with tempfile.TemporaryDirectory() as d:
            j=JobManager(Path(d),{})
            with self.assertRaises(ValueError):j.start('real')
    def test_duplicate_job_and_stop_only_owned_process(self):
        with tempfile.TemporaryDirectory() as d:
            cmd=[sys.executable,'-c','import time; time.sleep(60)']
            other=subprocess.Popen(cmd)
            j=JobManager(Path(d),{'check':cmd})
            try:
                p=j.start('check')
                with self.assertRaises(RuntimeError):j.start('check')
                j.stop();self.assertIsNotNone(p.poll());self.assertIsNone(other.poll())
            finally:
                j.stop();other.terminate();other.wait(timeout=3)
    def test_nonzero_exit_is_failure_with_log(self):
        with tempfile.TemporaryDirectory() as d:
            j=JobManager(Path(d),{'check':[sys.executable,'-c','print("root cause"); raise SystemExit(7)']})
            p=j.start('check');p.wait(timeout=3)
            self.assertEqual(j.snapshot()['returncode'],7)
            self.assertIn('root cause',j.log.read_text())

if __name__=='__main__':unittest.main()
