import unittest
from unittest.mock import patch,Mock
from official_sonic.streamer import Dex1InputReader

class TriggerSnapshotTests(unittest.TestCase):
    def test_trigger_uses_same_accepted_body_packet(self):
        reader=object.__new__(Dex1InputReader)
        reader.publisher=Mock();reader.trigger_sequence=0;reader.last_trigger_at=None
        import threading
        reader.lock=threading.Lock();reader.controllers={}
        sample={'timestamp_monotonic':10.,'pico_controllers':{'left':{'trigger':.2},'right':{'trigger':.7}}}
        with patch('sim_teleop.process_reader.ProcessPicoReader.get_latest',return_value=sample):
            self.assertIs(reader.get_latest(),sample)
        self.assertIn(b'"left": 0.2',reader.publisher.send.call_args.args[0])
        self.assertIn(b'"right": 0.7',reader.publisher.send.call_args.args[0])

class InvalidHandInputIsolationTests(unittest.TestCase):
    def test_invalid_trigger_does_not_discard_valid_body_sample(self):
        reader=object.__new__(Dex1InputReader)
        reader.publisher=Mock();reader.trigger_sequence=0;reader.last_trigger_at=None
        for value in (None,float('nan'),2.):
            sample={'timestamp_monotonic':10.,'pico_controllers':{'left':{'trigger':value},'right':{'trigger':0.}}}
            with patch('sim_teleop.process_reader.ProcessPicoReader.get_latest',return_value=sample):
                self.assertIs(reader.get_latest(),sample)
        reader.publisher.send.assert_not_called()
        self.assertEqual(reader.trigger_sequence,0)
