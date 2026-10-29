import json,tempfile,time,unittest
from pathlib import Path
import cv2
import numpy as np
from capture.workbench import quality
from capture.core import make_frame,REQUIRED
from capture.tests.test_contract import sample

class QualityTests(unittest.TestCase):
    def make(self,root):
        now=time.monotonic_ns();s=sample()
        for v in s.values():v['mono_ns']=now
        frame=make_frame(s,now)
        for role,name in frame['images'].items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);cv2.imwrite(str(p),np.zeros((8,8,3),dtype=np.uint8))
        (root/'episode.json').write_text(json.dumps({'complete':True,'frames':1}))
        (root/'frames.jsonl').write_text(json.dumps(frame)+'\n')
        events=[{'topic':k,'data':{'token_state':[.1]*64} if k=='g1_debug' else {}} for k in REQUIRED]
        (root/'events.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in events));return frame
    def test_structure_success_never_approves_training(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.make(p);q=quality(p)
            self.assertEqual(q['result'],'PASS_STRUCTURAL');self.assertFalse(q['training_ready']);self.assertEqual(q['human_review'],'pending')
    def test_future_receipt_and_missing_command_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);f=self.make(p);f['source_receipts']['g1_debug']['mono_ns']=f['mono_ns']+1
            del f['source_receipts']['dex1_left_cmd'];(p/'frames.jsonl').write_text(json.dumps(f)+'\n')
            q=quality(p);self.assertEqual(q['result'],'FAIL');self.assertIn('future/stale g1_debug',q['errors'])
    def test_missing_tokens_or_images_are_not_structural_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);f=self.make(p);(p/'events.jsonl').write_text('');(p/f['images']['ego_view']).unlink()
            q=quality(p);self.assertEqual(q['result'],'FAIL');self.assertEqual(q['valid_64d_token_events'],0)
