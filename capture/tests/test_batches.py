import json,tempfile,unittest
from pathlib import Path
from capture import batches

class BatchTests(unittest.TestCase):
    def test_finish_resets_display_count_without_touching_episodes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ep=root/'SESSION_old/episode_000000';ep.mkdir(parents=True)
            (ep/'episode.json').write_text('{"take_number":9}')
            before=(ep/'episode.json').read_bytes()
            (root/'take-counter.json').write_text('{"last_number":10}')
            closed=batches.finish(root)
            self.assertEqual(closed['last_number'],10)
            first=batches.allocate(root);second=batches.allocate(root)
            self.assertEqual((first['last_number'],second['last_number']),(1,2))
            self.assertNotEqual(first['batch_id'],'legacy')
            self.assertEqual((ep/'episode.json').read_bytes(),before)
            self.assertEqual(len(list((root/'.batches').glob('*.json'))),1)
    def test_allocation_preserves_old_numbers_until_explicit_finish(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'take-counter.json').write_text('{"last_number":10}')
            self.assertEqual(batches.allocate(root)['last_number'],11)
    def test_corrupt_counter_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'take-counter.json').write_text('{"last_number":-1}')
            with self.assertRaises(ValueError):batches.allocate(root)
    def test_catalog_never_calls_retained_episodes_approved(self):
        from capture.workbench import catalog
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ep=root/'SESSION_old/episode_000000';ep.mkdir(parents=True)
            (ep/'episode.json').write_text('{"take_number":9,"frames":343,"complete":true}')
            (ep/'context.json').write_text('{"session":{"task":"test","fps":15}}')
            row=catalog(root)[0]
            self.assertEqual(row['decision'],'pending');self.assertEqual(row['number'],9)
    def test_finish_live_episode_saves_before_reset(self):
        from capture.record import Capture
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=Capture(root/'SESSION_1',15,'test',{})
            c.request('finish_batch')
            self.assertEqual(json.loads((root/'take-counter.json').read_text())['last_number'],0)
            c.close()

class BatchLifecycleIntegrationTests(unittest.TestCase):
    def test_finish_saves_active_episode_then_next_start_is_one_without_overwrite(self):
        import time
        from capture.record import Capture
        from capture.core import make_frame
        from capture.tests.test_contract import sample
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'SESSION_1',15,'test',{'synthetic':True})
            def ready():
                c.latest=sample()
                for v in c.latest.values():v['mono_ns']=time.monotonic_ns()
            ready();c.request('start');original=c.ep.path;c.ep.append(make_frame(c.latest,time.monotonic_ns()))
            c.request('finish_batch');first=(original/'episode.json').read_bytes()
            ready();c.request('start');self.assertEqual(c.take_number,1)
            self.assertNotEqual(c.ep.path,original);self.assertEqual((original/'episode.json').read_bytes(),first)
            self.assertNotEqual(c.batch_id,json.loads(first)['batch_id']);c.close()
    def test_offline_reset_refuses_active_recorder_lock(self):
        import fcntl,sys
        sys.path.insert(0,'/opt/g1/GR00T-WholeBodyControl')
        from official_sonic.console.data_manager import finish_idle
        from official_sonic.console.backend import Config
        from unittest.mock import patch
        from official_sonic.console import data_manager
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'capture').mkdir()
            with patch.object(data_manager,'CAPTURE_HOME',root):
                with (root/'capture/recorder.lock').open('a') as f:
                    fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaises(RuntimeError):finish_idle(Config())
