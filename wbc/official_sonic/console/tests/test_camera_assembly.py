import unittest,queue,sys,types
# Driver imports stay lazy; this is the upstream queue assembler, no cameras.
from gear_sonic.camera.composed_camera import ComposedCameraSensor
class CameraAssemblyTests(unittest.TestCase):
 def test_staggered_frames_are_not_discarded(self):
  c=ComposedCameraSensor.__new__(ComposedCameraSensor);c.camera_queues={k:queue.Queue() for k in ['ego_view','left_wrist','right_wrist']};c._check_for_errors=lambda:None
  c.camera_queues['ego_view'].put({'id':'head'})
  self.assertIsNone(c.read())
  c.camera_queues['left_wrist'].put({'id':'left'});c.camera_queues['right_wrist'].put({'id':'right'})
  data=c.read();self.assertIsNotNone(data);self.assertEqual(set(data),set(c.camera_queues));self.assertIsNone(c.read())
