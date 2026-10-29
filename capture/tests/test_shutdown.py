import unittest
from capture import record

class ShutdownTests(unittest.TestCase):
    def outcome(self,status,requested,interrupted=False):
        self.assertTrue(callable(getattr(record,'shutdown_outcome',None)))
        return record.shutdown_outcome(status,requested,interrupted)
    def test_normal_stop_does_not_require_a_stopped_controller_to_keep_streaming(self):
        status={'ready':False,'blocked_reason':'stale g1_debug','faults':{},'saved_episodes':2}
        result=self.outcome(status,True)
        self.assertEqual(result['exit_code'],0)
        self.assertFalse(result['stream_ready_at_exit'])
    def test_fault_or_interrupted_episode_remains_failure(self):
        for status,interrupted in [({'ready':False,'faults':{'DDS queue overflow':1}},False),({'ready':True,'faults':{}},True)]:
            self.assertEqual(self.outcome(status,True,interrupted)['exit_code'],2)
    def test_unexpected_unready_end_does_not_become_success(self):
        self.assertEqual(self.outcome({'ready':False,'faults':{}},False)['exit_code'],2)
