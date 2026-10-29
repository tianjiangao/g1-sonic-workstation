import unittest
import numpy as np
from scipy.spatial.transform import Rotation
import torch
from gear_sonic.scripts.pico_manager_thread_server import compute_from_body_poses

PARENTS=[-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19,20,21]
class MappingTests(unittest.TestCase):
 def test_left_right_elbows_remain_on_their_own_sides(self):
  neutral=np.zeros((24,7));neutral[:,6]=1
  base=compute_from_body_poses(PARENTS,torch.device('cpu'),neutral)['smpl_pose'].numpy().reshape(23,3)
  for changed,opposite in [(18,[17,19,21]),(19,[16,18,20])]:
   pose=neutral.copy();pose[changed,3:]=Rotation.from_rotvec([.3,0,0]).as_quat()
   out=compute_from_body_poses(PARENTS,torch.device('cpu'),pose)['smpl_pose'].numpy().reshape(23,3)
   self.assertGreater(np.linalg.norm(out[changed-1]-base[changed-1]),.2)
   for j in opposite:np.testing.assert_allclose(out[j-1],base[j-1],atol=1e-6)
if __name__=='__main__':unittest.main()

class LowerBodyMappingTests(unittest.TestCase):
 def test_both_legs_reach_their_own_smpl_joint_channels(self):
  neutral=np.zeros((24,7));neutral[:,6]=1
  base=compute_from_body_poses(PARENTS,torch.device('cpu'),neutral)['smpl_pose'].numpy().reshape(23,3)
  for changed,other_leg in [(1,[2,5,8]),(4,[2,5,8]),(7,[2,5,8]),(2,[1,4,7]),(5,[1,4,7]),(8,[1,4,7])]:
   with self.subTest(joint=changed):
    pose=neutral.copy();pose[changed,3:]=Rotation.from_rotvec([.2,0,0]).as_quat()
    out=compute_from_body_poses(PARENTS,torch.device('cpu'),pose)['smpl_pose'].numpy().reshape(23,3)
    self.assertGreater(np.linalg.norm(out[changed-1]-base[changed-1]),.15)
    for j in other_leg:np.testing.assert_allclose(out[j-1],base[j-1],atol=1e-6)
 def test_world_translation_is_not_a_robot_walk_distance_command(self):
  neutral=np.zeros((24,7));neutral[:,6]=1
  shifted=neutral.copy();shifted[:,:3]+=[2,0,0]
  base=compute_from_body_poses(PARENTS,torch.device('cpu'),neutral)
  moved=compute_from_body_poses(PARENTS,torch.device('cpu'),shifted)
  np.testing.assert_allclose(base['smpl_joints_local'],moved['smpl_joints_local'],atol=1e-6)
