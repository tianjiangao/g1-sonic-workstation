import threading
import time
import unittest
from official_sonic.unitree_dex1 import OfficialLoop

class OfficialLoopTests(unittest.TestCase):
    def test_exact_upstream_loop_closes_only_selected_side_and_limits_step(self):
        records={'left':[],'right':[]};event=threading.Event()
        def publish(side,msg):
            records[side].append((msg.cmds[0].q,msg.cmds[0].kp,msg.cmds[0].kd))
            if len(records['left'])>=5 and len(records['right'])>=5:event.set()
        loop=OfficialLoop(publish);loop.set_state('left',2.8);loop.set_state('right',2.4)
        loop.set_input(5.,5.+2.*2.4/5.4,True)
        try:
            loop.start();self.assertTrue(event.wait(1),'official control thread produced no output')
        finally:loop.stop()
        self.assertFalse(loop.thread.is_alive())
        self.assertTrue(all(2.62-1e-6<=q<2.8 for q,_,_ in records['left']))
        self.assertTrue(all(abs(q-2.4)<1e-6 for q,_,_ in records['right']))
        self.assertEqual(records['left'][0][1:],(5.,.05))

if __name__=='__main__':unittest.main()

class FilterSettlingTests(unittest.TestCase):
    def test_repeated_endpoint_advances_history_until_exact_target(self):
        import numpy as np
        from official_sonic import unitree_dex1 as adapter
        self.assertTrue(hasattr(adapter,'SampledFilter'),'Repeated endpoint settling is missing')
        cls=adapter.load_official()['WeightedMovingFilter']
        f=adapter.SampledFilter(cls(np.array([.5,.3,.2]),2))
        for q in (5.0,5.2,5.4,5.4,5.4):f.add_data(np.array([q,q]))
        np.testing.assert_allclose(f.filtered_data,[5.4,5.4],atol=1e-8)
