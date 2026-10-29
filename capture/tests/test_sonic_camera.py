import unittest,base64,msgpack,cv2,numpy as np
from capture.sonic_camera import packets
from gear_sonic.camera.sensor_server import ImageMessageSchema
class SonicCameraTests(unittest.TestCase):
 def test_official_three_roles_raw_and_base64_preserve_rgb(self):
  red=np.full((16,16,3),(255,0,0),np.uint8)
  legacy=ImageMessageSchema({'ego_view':1.},{'ego_view':red}).serialize()['images']['ego_view']
  raw=cv2.imencode('.jpg',red[:,:,::-1])[1].tobytes()
  data={'images':{'ego_view':legacy,'left_wrist':raw,'right_wrist':raw},'timestamps':{'ego_view':1.,'left_wrist':2.,'right_wrist':3.}}
  rows=list(packets(msgpack.packb(data,use_bin_type=True)));self.assertEqual([x[0] for x in rows],['camera_head','camera_left','camera_right']);self.assertEqual(rows[1][2],2.)
  for _,jpeg,_ in rows:
   bgr=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR);self.assertGreater(bgr[8,8,2],220);self.assertLess(bgr[8,8,0],20)
 def test_bad_jpeg_refused(self):
  with self.assertRaises(ValueError):list(packets(msgpack.packb({'images':{'ego_view':b'bad'},'timestamps':{'ego_view':1.}},use_bin_type=True)))
 def test_bad_timestamp_refused(self):
  with self.assertRaises(ValueError):list(packets(msgpack.packb({'images':{'ego_view':b'\xff\xd8x'},'timestamps':{'ego_view':float('nan')}},use_bin_type=True)))
