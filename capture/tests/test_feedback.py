import json
from pathlib import Path
import tempfile
import time
import unittest
from capture.record import Capture
from capture.tests.test_contract import sample

class FeedbackTests(unittest.TestCase):
    def ready(self,c):
        c.latest=sample()
        for v in c.latest.values():v['mono_ns']=time.monotonic_ns()
        c.images={k:b'jpeg-placeholder' for k in ('camera_head','camera_left','camera_right')}
    def test_begin_and_saved_messages_follow_actual_disk_state(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'SESSION_1',15,'test',{'synthetic':True});self.ready(c);messages=[]
            c.announce=messages.append;c.request('start');c.request('start')
            self.assertEqual(len(list(c.root.glob('episode_*'))),1)
            c.ep.append(__import__('capture.core',fromlist=['make_frame']).make_frame(c.latest,time.monotonic_ns()))
            c.request('stop');meta=json.loads(next(c.root.glob('episode_*/episode.json')).read_text())
            self.assertTrue(meta['complete']);self.assertEqual(meta['take_number'],1)
            self.assertEqual(messages,['开始采集，第1条','采集结束，第1条已保存'])
            self.assertEqual(c.status()['saved_episodes'],1);c.close()
    def test_missing_inputs_announce_failure_and_create_no_episode(self):
        with tempfile.TemporaryDirectory() as d:
            c=Capture(Path(d)/'SESSION_1',15,'test',{});messages=[];c.announce=messages.append
            c.request('start');self.assertFalse(list(c.root.glob('episode_*')))
            self.assertIn('未开始采集',messages[0]);self.assertEqual(c.status()['last_event']['kind'],'blocked');c.close()
    def test_new_session_number_continues_and_fault_never_announces_saved(self):
        with tempfile.TemporaryDirectory() as d:
            for name,number in [('SESSION_1',1),('SESSION_2',2)]:
                c=Capture(Path(d)/name,15,'test',{});self.ready(c);messages=[];c.announce=messages.append
                c.request('start');self.assertIn(f'第{number}条',messages[-1]);c.fail('stale g1_debug')
                self.assertNotIn('已保存',messages[-1]);self.assertFalse(c.status()['recording']);c.close()
