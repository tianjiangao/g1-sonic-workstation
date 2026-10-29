import unittest
from sim_teleop.packet_reader import PacketGate

def packet(t,offset=0):
    return {'timeStampNs':t,'Body':{'joints':[{'p':f'{i+offset},0,0,0,0,0,1','t':0} for i in range(24)]}}

class PacketTests(unittest.TestCase):
    def test_full_body_updates_required(self):
        g=PacketGate();self.assertIsNone(g.update(packet(1),0))
        p=packet(2);p['Body']['joints'][15]['p']='15.1,0,0,0,0,0,1'
        self.assertIsNone(g.update(p,.02))
        self.assertIsNone(g.latest(.3));self.assertIn('stale',g.reason)
    def test_atomic_updates_accepted(self):
        g=PacketGate();g.update(packet(1),0)
        self.assertIsNotNone(g.update(packet(2,.1),.02))
    def test_replayed_envelope_rejected(self):
        g=PacketGate();g.update(packet(1),0);self.assertIsNone(g.update(packet(1,.1),.02))
    def test_missing_joint_rejected(self):
        p=packet(2);p['Body']['joints'].pop();g=PacketGate()
        self.assertIsNone(g.update(p,0))
    def test_nonfinite_rejected(self):
        p=packet(2);p['Body']['joints'][3]['p']='nan,0,0,0,0,0,1'
        self.assertIsNone(PacketGate().update(p,0))
    def test_bad_quaternion_rejected(self):
        p=packet(2);p['Body']['joints'][3]['p']='0,0,0,0,0,0,0'
        self.assertIsNone(PacketGate().update(p,0))
    def test_stale_sample_rejected(self):
        g=PacketGate();g.update(packet(1),0);g.update(packet(2,.1),.02)
        self.assertIsNone(g.latest(.28))
    def test_frozen_positive_imu_timestamp_rejected(self):
        g=PacketGate();p=packet(1)
        for j in p['Body']['joints']:j['t']=42
        g.update(p,0);p=packet(2,.1)
        for j in p['Body']['joints']:j['t']=42
        self.assertIsNone(g.update(p,.02))

if __name__=='__main__':unittest.main()
