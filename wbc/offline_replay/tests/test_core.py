import json,tempfile,unittest
from pathlib import Path
import numpy as np
from offline_replay import core

REAL=Path('/opt/g1/GR00T-WholeBodyControl/outputs/real_sessions/g1_demo/SESSION_20261028_095554_231880/episode_000000')
class ReplayTests(unittest.TestCase):
    def test_real_episode_uses_observation_not_targets_and_matches_raw_receipts(self):
        e=core.Episode(REAL)
        self.assertEqual(len(e.frames),558);self.assertEqual(e.kind,'REAL_CAPTURE')
        np.testing.assert_array_equal(e.frames[0]['q'],e.raw_first_observation)
        self.assertGreater(e.provenance_matches,550)
        self.assertGreater(np.max(np.abs(np.asarray(e.frames[0]['q'])-e.frames[0]['target'])),.001)
    def test_model_maps_each_named_joint_without_offsets_or_simulation(self):
        m=core.BodyModel();q=np.linspace(-.03,.03,29);m.apply(q)
        self.assertEqual(m.model.nu,0);self.assertEqual(m.model.nq,40)
        self.assertEqual(len(m.names),29);np.testing.assert_allclose(m.data.qpos[m.addresses],q)
        np.testing.assert_array_equal(m.data.qpos[:7],m.model.qpos0[:7]);self.assertEqual(m.data.time,0.)
        self.assertTrue(all(np.linalg.norm(x)==1 for x in m.axes))
    def test_wrong_dof_or_nonfinite_is_rejected(self):
        m=core.BodyModel()
        for q in ([0.]*28,[0.]*64,[float('nan')]*29,[float('inf')]*29):
            with self.assertRaises(ValueError):m.apply(q)
    def test_timestamp_seek_uses_last_frame_at_or_before_requested_time(self):
        e=core.Episode(REAL)
        self.assertEqual(e.seek(-1),0);self.assertEqual(e.seek(1e8),557)
        t=(e.times[10]+e.times[11])/2;self.assertEqual(e.seek(t),10)
    def test_missing_actual_state_never_falls_back_to_action(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'episode.json').write_text('{"complete":true,"frames":1}')
            (p/'context.json').write_text('{"session":{"synthetic":true},"latest":{}}')
            f={'mono_ns':1,'action.body':[0.]*29,'images':{}}
            (p/'frames.jsonl').write_text(json.dumps(f)+'\n');(p/'events.jsonl').write_text('')
            with self.assertRaises(ValueError):core.Episode(p)
