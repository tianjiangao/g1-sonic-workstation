import unittest,json,tempfile,bisect
from pathlib import Path
from sonic_pipeline.manifest import inventory,approved,fingerprint,sha
from sonic_pipeline.runner import gate
from sonic_pipeline.convert import Timeline,vector,schema
class TimelineTests(unittest.TestCase):
 def test_asof_never_uses_future_event(self):
  x=Timeline.__new__(Timeline);x.times={'g1_debug':[1_000_000_000,1_100_000_000]};x.events={'g1_debug':[{'mono_ns':t,'data':{'value':i}} for i,t in enumerate(x.times['g1_debug'])]}
  self.assertEqual(x.at('g1_debug',1_050_000_000)['data']['value'],0)
  with self.assertRaises(ValueError):x.at('g1_debug',999_000_000)
  with self.assertRaises(ValueError):x.at('g1_debug',1_400_000_000)
 def test_tokens_must_be_real64_dim_not_body29_or_nan(self):
  for v in [[0.]*29,[float('nan')]*64]:
   with self.assertRaises(ValueError):vector(v,64)
 def test_schema_keeps_real_two_grippers(self):
  f,m=schema();self.assertEqual(f['action.motion_token']['shape'],(64,));self.assertEqual(f['action.dex1']['shape'],(2,));self.assertNotIn('left_hand_joints',m['action'])
class GateTests(unittest.TestCase):
 def setup_files(self,p):
  (p/'data').mkdir();(p/'data/example.parquet').write_bytes(b'example');(p/'pipeline-provenance.json').write_text(json.dumps({'schema':'sonic_token64_dex1x2_v1','engineering_only':True,'human_approved':False}));(p/'reader-validation.json').write_text(json.dumps({'actual_gr00t_reader':'PASS','artifact_sha256':{'data/example.parquet':sha(p/'data/example.parquet')}}))
 def test_engineering_input_cannot_pass_formal_training_gate(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.setup_files(p)
   self.assertTrue(gate(p,smoke=True)['engineering_only'])
   with self.assertRaisesRegex(ValueError,'Engineering/unreviewed'):gate(p)
 def test_modified_validated_artifact_fails_before_training(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);self.setup_files(p);(p/'data/example.parquet').write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'artifacts changed'):gate(p,smoke=True)
 def test_unreviewed_manifest_not_auto_approved(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'review.json';p.write_text(json.dumps({'episodes':[{'decision':'unreviewed','split':'train'}]}))
   with self.assertRaisesRegex(ValueError,'No human-approved'):approved(p,'train')
 def test_review_requires_named_reviewer_and_reason(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'review.json';p.write_text(json.dumps({'episodes':[{'decision':'approved','split':'train'}]}))
   with self.assertRaisesRegex(ValueError,'reviewer'):approved(p,'train')
if __name__=='__main__':unittest.main()

class LauncherTests(unittest.TestCase):
 def test_8xl40_plan_uses_eight_torchrun_ranks_and_real_dex1_config(self):
  from unittest.mock import patch
  from sonic_pipeline.runner import training_plan
  with tempfile.TemporaryDirectory() as d:
   with patch('sonic_pipeline.runner.gate',return_value={}):p=training_plan('/dataset',Path(d)/'new_run','/base',8,False,'/validation')
   a=p['argv'];self.assertEqual(a[a.index('--nproc_per_node')+1],'8');self.assertEqual(a[a.index('--num-gpus')+1],'8');self.assertEqual(a[a.index('--global-batch-size')+1],'64');self.assertEqual(a[a.index('--embodiment-tag')+1],'NEW_EMBODIMENT');self.assertFalse(p['robot_control_started'])
 def test_training_output_never_overwritten(self):
  from unittest.mock import patch
  from sonic_pipeline.runner import training_plan
  with tempfile.TemporaryDirectory() as d:
   with patch('sonic_pipeline.runner.gate',return_value={}):
    with self.assertRaises(FileExistsError):training_plan('/dataset',d,'/base',8,False,'/validation')

class InferenceContractTests(unittest.TestCase):
 def test_real66d_contract_and_no_publishers(self):
  import numpy as np
  from sonic_pipeline.inference_contract import split_actions
  x=split_actions({'motion_token':np.zeros((1,40,64)),'left_gripper':np.ones((1,40,1)),'right_gripper':np.ones((1,40,1))})
  self.assertEqual(x['sonic_motion_token'].shape,(40,64));self.assertFalse(x['robot_control_started'])
 def test_invalid_prediction_is_rejected(self):
  import numpy as np
  from sonic_pipeline.inference_contract import split_actions
  for value in [float('nan'),6.]:
   with self.assertRaises(ValueError):split_actions({'motion_token':np.zeros((40,64)),'left_gripper':np.full((40,1),value),'right_gripper':np.ones((40,1))})

class PolicyTests(unittest.TestCase):
 def test_policy_tamper_stops_execution(self):
  import hashlib
  from unittest.mock import patch
  from sonic_pipeline.policy_guard import check_policy
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);root=home/'sonic_pipeline';root.mkdir()
   document=home/'AGENTS.md';document.write_text('fixed workflow')
   (root/'workflow-contract.json').write_text('{}')
   (root/'policy-lock.json').write_text(json.dumps({'files':{'AGENTS.md':hashlib.sha256(document.read_bytes()).hexdigest()}}))
   with patch('sonic_pipeline.policy_guard.HOME',home),patch('sonic_pipeline.policy_guard.ROOT',root):
    self.assertEqual(check_policy(),{})
    document.write_text('changed without approval')
    with self.assertRaisesRegex(ValueError,'policy changed'):check_policy()
 def test_cloud_paths_cannot_escape_approved_root(self):
  from unittest.mock import patch
  from sonic_pipeline.policy_guard import check_cloud_paths
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   with patch('sonic_pipeline.policy_guard.HOME',root),patch('sonic_pipeline.policy_guard.check_policy',return_value={'destination':{'root':d}}):
    check_cloud_paths([root/'datasets/train',root/'runs/new'])
    with self.assertRaisesRegex(ValueError,'escapes'):check_cloud_paths([root.parent/'outside'])
