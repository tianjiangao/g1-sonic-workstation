import unittest
import numpy as np
from scipy.spatial.transform import Rotation
from gear_sonic.trl.utils.rotation_conversion import decompose_rotation_aa,quaternion_multiply_np

class Tests(unittest.TestCase):
    def check(self,rotvec):
        r=np.asarray(rotvec,dtype=float).reshape(-1,3)
        t,s=decompose_rotation_aa(r,np.array([0.,1.,0.]))
        self.assertTrue(np.isfinite(t).all() and np.isfinite(s).all())
        np.testing.assert_allclose(np.linalg.norm(t,axis=1),1,atol=1e-12)
        np.testing.assert_allclose(np.linalg.norm(s,axis=1),1,atol=1e-12)
        q=quaternion_multiply_np(t,s)
        np.testing.assert_allclose(Rotation.from_quat(q[:,[1,2,3,0]]).as_matrix(),Rotation.from_rotvec(r).as_matrix(),atol=1e-12)
    def test_zero_rotation(self):self.check([[0,0,0]])
    def test_near_zero(self):self.check([[1e-15,0,0],[0,1e-15,0]])
    def test_pi_perpendicular_to_twist_axis(self):self.check([[np.pi,0,0]])
    def test_general_rotations(self):self.check(np.random.default_rng(18).normal(size=(50,3)))
if __name__=='__main__':unittest.main()
