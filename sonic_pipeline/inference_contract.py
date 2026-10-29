"""Pure offline66D action/preprocessing contract. No DDS/ZMQ/motor publishers."""
import numpy as np

def split_actions(actions):
 result={}
 for key,width in [('motion_token',64),('left_gripper',1),('right_gripper',1)]:
  value=np.asarray(actions.get(key,actions.get('action.'+key)),dtype=np.float32)
  if value.ndim==3 and value.shape[0]==1:value=value[0]
  if value.shape!=(40,width) or not np.isfinite(value).all():raise ValueError('Invalid predicted '+key)
  if width==1 and not np.all((value>=0)&(value<=5.4)):raise ValueError('Predicted Dex1 target outside calibrated command range')
  result[key]=value.copy()
 return {'sonic_motion_token':result['motion_token'],'dex1_left_q':result['left_gripper'],'dex1_right_q':result['right_gripper'],'robot_control_started':False,'physical_execution_verified':False}

def preprocess_views(images):
 result={}
 for key in ['ego_view','left_wrist','right_wrist']:
  image=np.asarray(images[key]);expected=(480,1280,3) if key=='ego_view' else (480,640,3)
  if image.shape!=expected or image.dtype!=np.uint8:raise ValueError('Wrong RGB input '+key)
  result[key]=(image[:,:640] if key=='ego_view' else image).copy()
 return result
