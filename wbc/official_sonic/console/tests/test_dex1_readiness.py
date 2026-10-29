import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from official_sonic import run_real_teleop as entry

class Dex1ReadinessTests(unittest.TestCase):
 def check(self,state,process_code=None):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'dex1.json';p.write_text(json.dumps({'result':'WAITING','state':state}))
   child=SimpleNamespace(poll=lambda:process_code)
   return entry.wait_for_dex1_feedback(p,child,timeout=0,clock=lambda:10.,pause=lambda _:None)
 def test_both_fresh_feedback_allows_controller_start_without_sending_commands(self):
  state={k:{'q':q,'dq':0.,'tau_est':0.,'at':9.99} for k,q in [('left',5.3),('right',5.2)]}
  self.assertEqual(set(self.check(state)['state']),{'left','right'})
 def test_missing_physical_left_does_not_silently_start_body(self):
  with self.assertRaisesRegex(RuntimeError,'左夹爪.*反馈'):
   self.check({'right':{'q':5.3,'dq':0.,'tau_est':0.,'at':9.99}})
 def test_stale_or_nonfinite_feedback_cannot_pass(self):
  for value in [8.,float('nan')]:
   with self.assertRaises(RuntimeError):
    self.check({k:{'q':5.3,'dq':0.,'tau_est':0.,'at':value} for k in ('left','right')})
 def test_exited_bridge_cannot_pass(self):
  with self.assertRaisesRegex(RuntimeError,'退出'):
   self.check({},1)
