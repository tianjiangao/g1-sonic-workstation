import unittest
from official_sonic import run_real_teleop as runner

class ConsoleLogFilterTests(unittest.TestCase):
    def test_verbose_frames_are_compacted_but_alarms_and_transitions_are_kept(self):
        self.assertTrue(callable(getattr(runner,'console_control_line',None)))
        for line in ['  Frame[10] joint_pos: [0,1]','[ZMQEndpointInterface] Decoded body quaternions: 1 bodies per frame','[StreamedMotionMerger] Processing 10 frames']:
            self.assertFalse(runner.console_control_line(line))
        for line in ['[HighTemp] Right Ankle Pitch(90)','[ZMQEndpointInterface] ERROR invalid packet','Init Done','[ZMQManager] Mode -> 1: SLOW_WALK','[StreamedMotionMerger] Warning frame gap','Stop']:
            self.assertTrue(runner.console_control_line(line))
